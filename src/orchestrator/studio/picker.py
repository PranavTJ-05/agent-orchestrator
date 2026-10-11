from __future__ import annotations

import asyncio
import re
import time
from collections import OrderedDict

from pydantic import BaseModel

from .jev import JevScorer
from .models import ToolInfo

TOP_K = 4
SINGLE_STAGE_MAX_TOOLS = 8        # one pass over every tool stays under ~350 tokens
LOW_CONFIDENCE = 0.40
STOPWORDS = {"the", "a", "an", "to", "of", "and", "or", "in", "on", "for", "with", "my", "me", "is", "it",
             "this", "that", "what", "how", "do", "i", "you", "please", "get", "from", "at", "be"}


class PickedTool(BaseModel):
    qualified: str
    server_id: str
    name: str
    probability: float


class PickResult(BaseModel):
    tools: list[PickedTool]
    method: str            # "all" | "jev" | "jev-two-stage" | "keyword"
    confidence: float      # probability of the top choice (1.0 when nothing had to be chosen)
    low_confidence: bool
    ms: float


def _first_sentence(text: str, limit: int = 110) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    cut = re.split(r"(?<=[.!?])\s", text, maxsplit=1)[0]
    return cut[:limit].rstrip()


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", text.lower().replace("_", " ")) if w not in STOPWORDS}


class ToolPicker:
    """Chooses the few tools worth showing the LLM, so cost stays flat as servers are added.

    1. Few tools: nothing to choose, return them all.
    2. Jev model available: score all tools in one pass (<= 8 tools) or choose a server first,
       then the tool inside it (two-stage). The probabilities are calibrated.
    3. Otherwise: keyword overlap ranking.
    """

    def __init__(self, scorer: JevScorer | None = None, cache_size: int = 128) -> None:
        self.scorer = scorer if scorer is not None else JevScorer()
        self._cache: OrderedDict[tuple, PickResult] = OrderedDict()
        self._cache_size = cache_size

    async def pick(self, task: str, tools: list[ToolInfo], k: int = TOP_K,
                   always_rank: bool = False) -> PickResult:
        """Shortlist tools for a task. always_rank skips the "few tools, return all" shortcut (previews)."""
        started = time.monotonic()
        if not tools:
            return PickResult(tools=[], method="all", confidence=1.0, low_confidence=False, ms=0)
        if len(tools) <= k and (len(tools) == 1 or not always_rank):
            return self._result([(t, 1.0) for t in tools], "all", 1.0, started)
        key = (task.strip().lower(), tuple(sorted(t.qualified for t in tools)), k, always_rank)
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]
        if self.scorer.available():
            try:
                result = await asyncio.to_thread(self._jev, task, tools, k, started)
            except Exception:  # model failed to load or run: degrade, don't break the run
                result = self._keyword(task, tools, k, started)
        else:
            result = self._keyword(task, tools, k, started)
        self._cache[key] = result
        if len(self._cache) > self._cache_size:
            self._cache.popitem(last=False)
        return result

    # ---- strategies --------------------------------------------------------------
    def _jev(self, task: str, tools: list[ToolInfo], k: int, started: float) -> PickResult:
        if len(tools) <= SINGLE_STAGE_MAX_TOOLS:
            return self._jev_tools(task, tools, k, started, "jev")
        servers: dict[str, list[ToolInfo]] = {}
        for t in tools:
            servers.setdefault(t.server_id, []).append(t)
        if len(servers) == 1:
            return self._jev_tools(task, tools, k, started, "jev")
        ids = list(servers)
        opts = [f"{sid}: " + ", ".join(t.name.replace("_", " ") for t in ts[:6]) for sid, ts in servers.items()]
        probs = self.scorer.decide(task, "Which service is needed to do this task?", opts)
        ranked = sorted(zip(ids, probs), key=lambda x: -x[1])
        chosen = [ranked[0][0]] + ([ranked[1][0]] if ranked[0][1] < 0.6 and len(ranked) > 1 else [])
        pool = [t for sid in chosen for t in servers[sid]]
        result = self._jev_tools(task, pool, k, started, "jev-two-stage")
        result.confidence = round(result.confidence * ranked[0][1], 4)
        result.low_confidence = result.confidence < LOW_CONFIDENCE
        return result

    def _jev_tools(self, task: str, tools: list[ToolInfo], k: int, started: float, method: str) -> PickResult:
        opts = [f"{t.server_id}.{t.name}: {_first_sentence(t.description) or t.name.replace('_', ' ')}"
                for t in tools]
        probs = self.scorer.decide(task, "Which tool should be used to do this task?", opts)
        ranked = sorted(zip(tools, probs), key=lambda x: -x[1])[:k]
        return self._result(ranked, method, ranked[0][1], started)

    def _keyword(self, task: str, tools: list[ToolInfo], k: int, started: float) -> PickResult:
        q = _words(task)
        scored = []
        for t in tools:
            overlap = len(q & _words(f"{t.name} {t.description}"))
            scored.append((t, overlap / (1 + len(q))))
        ranked = sorted(scored, key=lambda x: -x[1])[:k]
        top = ranked[0][1]
        return self._result(ranked, "keyword", top, started, force_low=top < 0.2)

    @staticmethod
    def _result(ranked: list[tuple[ToolInfo, float]], method: str, confidence: float, started: float,
                force_low: bool = False) -> PickResult:
        return PickResult(
            tools=[PickedTool(qualified=t.qualified, server_id=t.server_id, name=t.name,
                              probability=round(p, 4)) for t, p in ranked],
            method=method, confidence=round(confidence, 4),
            low_confidence=force_low or confidence < LOW_CONFIDENCE,
            ms=round((time.monotonic() - started) * 1000),
        )

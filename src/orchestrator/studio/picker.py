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
SPLIT_SERVER_OVER = 10            # a server with more tools than this is split into groups for stage 1
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


def _is_advanced(tool: ToolInfo) -> bool:
    """Servers sometimes flag low-level twins of a friendlier tool ("ADVANCED, most callers should use X")."""
    text = (tool.description or "").lower()
    return text.startswith("advanced") or "most callers should use" in text


def _object_of(tool_name: str) -> str:
    """What a tool acts on: its last word, singularised (create_diagram, list_diagrams -> diagram)."""
    word = tool_name.rsplit("_", 1)[-1]
    return word[:-1] if len(word) > 4 and word.endswith("s") else word


def _words(text: str) -> set[str]:
    """Lower-cased content words with a trailing plural 's' removed ("files" matches "file")."""
    found = re.findall(r"[a-z0-9]+", text.lower().replace("_", " "))
    return {(w[:-1] if len(w) > 3 and w.endswith("s") else w) for w in found if w not in STOPWORDS}


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
                result = await asyncio.to_thread(self._jev, task, tools, k, started, always_rank)
            except Exception:  # model failed to load or run: degrade, don't break the run
                result = self._keyword(task, tools, k, started)
        else:
            result = self._keyword(task, tools, k, started)
        self._cache[key] = result
        if len(self._cache) > self._cache_size:
            self._cache.popitem(last=False)
        return result

    def keyword_pick(self, task: str, tools: list[ToolInfo], k: int = 3) -> PickResult:
        """Public keyword ranking (word overlap with tool names and descriptions)."""
        return self._keyword(task, tools, k, time.monotonic())

    # ---- strategies --------------------------------------------------------------
    def _groups(self, tools: list[ToolInfo]) -> dict[str, tuple[str, list[ToolInfo]]]:
        """Stage-1 groups: one per server, except big servers are split by what their tools act on
        (create_diagram, get_diagram -> "diagram"), so no single prompt has to list dozens of tools."""
        by_server: dict[str, list[ToolInfo]] = {}
        for t in tools:
            by_server.setdefault(t.server_id, []).append(t)
        groups: dict[str, tuple[str, list[ToolInfo]]] = {}
        for sid, ts in by_server.items():
            if len(ts) <= SPLIT_SERVER_OVER:
                groups[sid] = (f"{sid}: " + ", ".join(t.name.replace("_", " ") for t in ts[:6]), ts)
                continue
            by_object: dict[str, list[ToolInfo]] = {}
            for t in ts:
                by_object.setdefault(_object_of(t.name), []).append(t)
            for obj, members in by_object.items():
                verbs = ", ".join(dict.fromkeys(m.name.rsplit("_", 1)[0].replace("_", " ") if "_" in m.name else m.name
                                                for m in members))[:60]
                gist = _first_sentence(min((m.description for m in members if m.description), key=len, default=""), 60)
                groups[f"{sid}:{obj}"] = (f"{sid} {obj}: {verbs}" + (f"; {gist}" if gist else ""), members)
        return groups

    def _jev(self, task: str, tools: list[ToolInfo], k: int, started: float, wide: bool = False) -> PickResult:
        if len(tools) <= SINGLE_STAGE_MAX_TOOLS:
            return self._jev_tools(task, tools, k, started, "jev")
        groups = self._groups(tools)
        if len(groups) == 1:
            return self._jev_tools(task, tools, k, started, "jev")
        ids = list(groups)
        probs = self.scorer.decide(task, "Which service is needed to do this task?", [groups[g][0] for g in ids])
        ranked = sorted(zip(ids, probs), key=lambda x: -x[1])
        chosen = [ranked[0][0]]
        if ranked[0][1] < 0.6:  # not sure which group: keep a strong runner-up too (one keeps stage 2 small)
            chosen += [g for g, p in ranked[1:2] if p > 0.25]
        elif wide:  # capability lookups should also surface the neighbouring group (list_* next to search)
            chosen += [g for g, p in ranked[1:2] if p > 0.03]
        pool = [t for g in chosen for t in groups[g][1]]
        if len(pool) <= k:  # small enough for the LLM to choose from directly: skip the second model pass
            return self._result([(t, ranked[0][1]) for t in pool], "jev-two-stage", ranked[0][1], started)
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
        """Word overlap, weighted towards the tool's name (3x) over its first description sentence."""
        q = _words(task)
        scored = []
        for t in tools:
            name_hits = len(q & _words(t.name))
            desc_hits = len(q & _words(_first_sentence(t.description)))
            scored.append((t, (3 * name_hits + desc_hits) / (3 * len(q) + 1)))
        ranked = sorted(scored, key=lambda x: -x[1])[:k]
        top = ranked[0][1]
        return self._result(ranked, "keyword", top, started, force_low=top < 0.2)

    @staticmethod
    def _result(ranked: list[tuple[ToolInfo, float]], method: str, confidence: float, started: float,
                force_low: bool = False) -> PickResult:
        ranked = sorted(ranked, key=lambda pair: _is_advanced(pair[0]))  # stable: advanced twins go last
        return PickResult(
            tools=[PickedTool(qualified=t.qualified, server_id=t.server_id, name=t.name,
                              probability=round(p, 4)) for t, p in ranked],
            method=method, confidence=round(confidence, 4),
            low_confidence=force_low or confidence < LOW_CONFIDENCE,
            ms=round((time.monotonic() - started) * 1000),
        )

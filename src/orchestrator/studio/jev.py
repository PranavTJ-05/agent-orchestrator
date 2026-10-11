from __future__ import annotations

import math
import os
import threading
from pathlib import Path

DEFAULT_MODEL = "models/Jev-Style-0.8B-Decision-v3-Q4_K_M.gguf"
GLOBAL_TEMPERATURE = 0.880  # fallback calibration temperature from the model card
HEAD_BUDGET_TOKENS = 1800   # the card limits question + options + readout to 2,048 tokens


class JevScorer:
    """System-1 decision model (Jev-Style 0.8B v3, GGUF) run on CPU with llama-cpp-python.

    Input format and readout follow the model card: one forward pass over
    "State / Question / Options / Judge each option", then for every option the score is
    logit(" yes") - logit(" no") at the " ->" token that ends its line.
    """

    def __init__(self, model_path: str | None = None, n_threads: int | None = None) -> None:
        self.model_path = Path(model_path or os.getenv("JEV_MODEL_PATH", DEFAULT_MODEL))
        self.n_threads = n_threads or max(1, (os.cpu_count() or 4))
        self._llm = None
        self._lock = threading.Lock()  # llama.cpp contexts are not thread-safe
        self._ids: tuple[int, int] | None = None
        self.load_error: str | None = None

    def available(self) -> bool:
        return self.model_path.exists() and self._try_import() and self.load_error is None

    @staticmethod
    def _try_import() -> bool:
        try:
            import llama_cpp  # noqa: F401
            return True
        except ImportError:
            return False

    def _load(self) -> None:
        if self._llm is not None:
            return
        from llama_cpp import Llama
        try:
            self._llm = Llama(
                model_path=str(self.model_path), n_ctx=4096, n_threads=self.n_threads,
                logits_all=True, verbose=False,
            )
            self._ids = (self._tok(" yes")[0], self._tok(" no")[0])
        except Exception as e:  # corrupt file, unsupported architecture, out of memory
            self.load_error = f"{type(e).__name__}: {e}"
            raise

    def _tok(self, text: str) -> list[int]:
        return self._llm.tokenize(text.encode("utf-8"), add_bos=False, special=False)

    def scores(self, state: str, question: str, options: list[str], qtype: str = "choice") -> list[float]:
        """Raw yes-minus-no score per option. Options are chunked to respect the head budget."""
        with self._lock:
            self._load()
            out: list[float] = []
            for chunk in self._chunks(options):
                out.extend(self._score_chunk(state, question, chunk, qtype))
            return out

    def _chunks(self, options: list[str]) -> list[list[str]]:
        chunks: list[list[str]] = []
        current: list[str] = []
        used = 0
        for opt in options:
            cost = 2 * len(self._tok(opt)) + 6  # each option appears twice (list + judge line)
            if current and used + cost > HEAD_BUDGET_TOKENS:
                chunks.append(current)
                current, used = [], 0
            current.append(opt)
            used += cost
        if current:
            chunks.append(current)
        return chunks

    def _score_chunk(self, state: str, question: str, options: list[str], qtype: str) -> list[float]:
        head = (f"State:\n{state}\n\nQuestion [{qtype}]: {question}\nOptions:\n"
                + "".join(f"- {o}\n" for o in options) + "Judge each option:\n")
        ids = self._tok(head)
        slots = []
        for o in options:
            ids += self._tok(f"{o} ->")
            slots.append(len(ids) - 1)
            ids += self._tok("\n")
        if len(ids) > 3900:
            raise ValueError(f"decision prompt too long ({len(ids)} tokens)")
        self._llm.reset()
        self._llm.eval(ids)
        yes, no = self._ids  # type: ignore[misc]
        return [float(self._llm.scores[s][yes] - self._llm.scores[s][no]) for s in slots]

    def warm(self) -> None:
        """Load the model and run one tiny decision so the first real pick isn't slow."""
        try:
            self.scores("warm up", "Which option?", ["a", "b"])
        except Exception:
            pass  # load_error is recorded; the picker falls back to keywords

    def decide(self, state: str, question: str, options: list[str],
               temperature: float = GLOBAL_TEMPERATURE) -> list[float]:
        """Calibrated probability per option (softmax over scores / T)."""
        raw = self.scores(state, question, options)
        z = [s / temperature for s in raw]
        m = max(z)
        e = [math.exp(v - m) for v in z]
        total = sum(e)
        return [v / total for v in e]

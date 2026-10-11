import pytest

from orchestrator.agents.router import RouterAgent
from orchestrator.agents.synthesizer import MAX_CHARS_PER_RESULT, MAX_CHARS_TOTAL, SynthesizerAgent
from orchestrator.core.task import TaskNode
from orchestrator.llm import LLMConfig, MockLLM, create_llm
from orchestrator.llm.base import LLMUsage
from orchestrator.memory.long_term import HashEmbeddingFunction
from orchestrator.tools.search import _clean, _real_url


class RecordingLLM(MockLLM):
    last_prompt = ""

    async def generate(self, system_prompt, messages=None, **kwargs):
        self.last_prompt = messages[0]["content"]
        return "ok", []


@pytest.mark.asyncio
async def test_synthesizer_prompt_is_bounded():
    llm = RecordingLLM(LLMConfig(provider="mock"))
    tasks = [TaskNode(id=f"t{i}", description="d", result="x" * 50_000) for i in range(10)]
    await SynthesizerAgent(llm).synthesize("goal", tasks)
    assert len(llm.last_prompt) < MAX_CHARS_TOTAL + 1000
    assert MAX_CHARS_PER_RESULT < MAX_CHARS_TOTAL


@pytest.mark.asyncio
async def test_router_maps_planner_names_without_llm_call():
    class Fake:
        def __init__(self, name):
            self.name, self.description, self.tools = name, "", []

    llm = RecordingLLM(LLMConfig(provider="mock"))
    router = RouterAgent(llm)
    router.register_agents([Fake("coding"), Fake("finance")])
    assert await router.select(TaskNode(id="t", description="x", agent="code")) == "coding"
    assert llm.last_prompt == ""  # no LLM call was made


def test_groq_and_gemini_need_keys(monkeypatch):
    monkeypatch.setattr("dotenv.load_dotenv", lambda *a, **k: False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    with pytest.raises(ValueError, match="GROQ_API_KEY"):
        create_llm(LLMConfig(provider="groq"))
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    assert create_llm(LLMConfig(provider="gemini")).client.api_key == "k"


def test_search_helpers():
    assert _real_url("//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fa&rut=1") == "https://example.com/a"
    assert _clean("<b>Tesla</b> &amp; SpaceX  ") == "Tesla & SpaceX"


def test_hash_embedding_is_deterministic_and_normalised():
    fn = HashEmbeddingFunction()
    a, b = fn(["tesla stock price", "tesla stock price"])
    assert list(a) == list(b)
    assert abs(sum(float(v) ** 2 for v in a) - 1.0) < 1e-6


def test_usage_totals():
    u = LLMUsage(prompt_tokens=3, completion_tokens=4)
    assert u.total_tokens == 7

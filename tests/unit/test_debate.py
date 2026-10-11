import pytest
from orchestrator.debate import DebateRunner, DebateType, DebateRound, DebateResult
from orchestrator.debate.types import JudgeDecision
from orchestrator.llm.mock_llm import MockLLM
from orchestrator.llm import LLMConfig


@pytest.mark.asyncio
async def test_debate_runner_critic_loop():
    llm = MockLLM(LLMConfig(provider="mock"))
    runner = DebateRunner(llm, max_rounds=2)
    
    result = await runner.run_critic_loop(
        topic="What is the best programming language?",
        initial_response="Python is the best because it's easy to learn.",
    )
    
    assert result.debate_type == DebateType.CRITIC_LOOP
    assert result.topic == "What is the best programming language?"
    assert len(result.rounds) > 0


@pytest.mark.asyncio
async def test_debate_runner_agent_vs_agent():
    llm = MockLLM(LLMConfig(provider="mock"))
    runner = DebateRunner(llm, max_rounds=2)
    
    result = await runner.run_agent_vs_agent(
        topic="Is AI dangerous?",
        agent_a_name="pro",
        agent_a_prompt="You argue in favor of the motion.",
        agent_b_name="con",
        agent_b_prompt="You argue against the motion.",
    )
    
    assert result.debate_type == DebateType.AGENT_VS_AGENT
    assert result.topic == "Is AI dangerous?"
    assert result.winner is not None


def test_debate_result_to_dict():
    result = DebateResult(
        topic="Test topic",
        debate_type=DebateType.AGENT_VS_AGENT,
    )
    result.rounds.append(DebateRound(1, "agent_a", "Argument A"))
    result.rounds.append(DebateRound(1, "agent_b", "Argument B"))
    result.winner = "agent_a"
    result.judge_score = 8.5
    result.judge_reasoning = "Good reasoning"
    
    result_dict = result.to_dict()
    assert result_dict["topic"] == "Test topic"
    assert result_dict["debate_type"] == "agent_vs_agent"
    assert result_dict["winner"] == "agent_a"
    assert result_dict["judge_score"] == 8.5
    assert len(result_dict["rounds"]) == 2


def test_judge_decision_parse():
    response = """WINNER: agent_a
SCORE: 9.0
REASONING: Clear and logical argument"""

    runner = DebateRunner(MockLLM(), max_rounds=1)
    decision = runner._parse_judge_response(response)
    
    assert decision.winner == "agent_a"
    assert decision.score == 9.0
    assert "Clear and logical" in decision.reasoning


def test_debate_types():
    assert DebateType.CRITIC_LOOP.value == "critic_loop"
    assert DebateType.AGENT_VS_AGENT.value == "agent_vs_agent"
    assert DebateType.RESEARCH_LOOP.value == "research_loop"
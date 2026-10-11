import pytest
from orchestrator.cost import CostTracker, TokenUsage, MODEL_PRICING


def test_cost_tracker_record():
    tracker = CostTracker()
    usage = TokenUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150)
    
    record = tracker.record(
        session_id="session_1",
        agent_name="planner",
        model="gpt-4",
        provider="openai",
        usage=usage,
    )
    
    assert record.session_id == "session_1"
    assert record.agent_name == "planner"
    assert record.usage.total_tokens == 150
    assert record.cost > 0


def test_cost_tracker_session_cost():
    tracker = CostTracker()
    
    tracker.record(
        session_id="session_1",
        agent_name="planner",
        model="gpt-4",
        provider="openai",
        usage=TokenUsage(prompt_tokens=100, completion_tokens=50),
    )
    tracker.record(
        session_id="session_1",
        agent_name="research",
        model="gpt-4",
        provider="openai",
        usage=TokenUsage(prompt_tokens=200, completion_tokens=100),
    )
    
    cost = tracker.get_session_cost("session_1")
    assert cost > 0


def test_cost_tracker_agent_cost():
    tracker = CostTracker()
    
    tracker.record(
        session_id="session_1",
        agent_name="planner",
        model="gpt-4",
        provider="openai",
        usage=TokenUsage(prompt_tokens=100, completion_tokens=50),
    )
    tracker.record(
        session_id="session_2",
        agent_name="planner",
        model="gpt-4",
        provider="openai",
        usage=TokenUsage(prompt_tokens=200, completion_tokens=100),
    )
    
    cost = tracker.get_agent_cost("planner")
    assert cost > 0


def test_cost_tracker_model_cost():
    tracker = CostTracker()
    
    tracker.record(
        session_id="session_1",
        agent_name="planner",
        model="gpt-4",
        provider="openai",
        usage=TokenUsage(prompt_tokens=100, completion_tokens=50),
    )
    
    cost = tracker.get_model_cost("openai", "gpt-4")
    assert cost > 0


def test_cost_tracker_get_records():
    tracker = CostTracker()
    
    tracker.record(
        session_id="session_1",
        agent_name="planner",
        model="gpt-4",
        provider="openai",
        usage=TokenUsage(prompt_tokens=100, completion_tokens=50),
    )
    tracker.record(
        session_id="session_2",
        agent_name="research",
        model="gpt-4",
        provider="openai",
        usage=TokenUsage(prompt_tokens=200, completion_tokens=100),
    )
    
    records = tracker.get_records()
    assert len(records) == 2
    
    records = tracker.get_records(session_id="session_1")
    assert len(records) == 1
    
    records = tracker.get_records(agent_name="planner")
    assert len(records) == 1


def test_cost_tracker_summary():
    tracker = CostTracker()
    
    tracker.record(
        session_id="session_1",
        agent_name="planner",
        model="gpt-4",
        provider="openai",
        usage=TokenUsage(prompt_tokens=100, completion_tokens=50),
    )
    tracker.record(
        session_id="session_1",
        agent_name="research",
        model="gpt-4",
        provider="openai",
        usage=TokenUsage(prompt_tokens=200, completion_tokens=100),
    )
    
    summary = tracker.get_summary()
    assert summary["total_cost"] > 0
    assert summary["total_requests"] == 2
    assert "session_1" in summary["session_costs"]
    assert "planner" in summary["agent_costs"]


def test_cost_tracker_clear():
    tracker = CostTracker()
    
    tracker.record(
        session_id="session_1",
        agent_name="planner",
        model="gpt-4",
        provider="openai",
        usage=TokenUsage(prompt_tokens=100, completion_tokens=50),
    )
    
    tracker.clear()
    
    assert tracker.get_total_cost() == 0
    assert len(tracker.get_records()) == 0


def test_model_pricing():
    assert "huggingface" in MODEL_PRICING
    assert "openai" in MODEL_PRICING
    assert "gpt-4" in MODEL_PRICING["openai"]
    assert MODEL_PRICING["openai"]["gpt-4"]["input"] > 0


def test_token_usage():
    usage = TokenUsage(prompt_tokens=100, completion_tokens=50)
    assert usage.total_tokens == 150
    assert usage.input_tokens == 100
    assert usage.output_tokens == 50
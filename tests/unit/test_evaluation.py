import pytest
from orchestrator.evaluation import AgentEvaluator, TaskEvaluation, AgentMetrics, SessionEvaluation


def test_evaluator_record_task():
    evaluator = AgentEvaluator()
    
    evaluator.record_task(
        task_id="t1",
        agent_name="planner",
        session_id="session_1",
        success=True,
        duration_ms=1000.0,
    )
    
    metrics = evaluator.get_agent_metrics("planner")
    assert metrics["total_tasks"] == 1
    assert metrics["successful_tasks"] == 1
    assert metrics["success_rate"] == 1.0


def test_evaluator_record_task_failure():
    evaluator = AgentEvaluator()
    
    evaluator.record_task(
        task_id="t1",
        agent_name="planner",
        session_id="session_1",
        success=False,
        duration_ms=1000.0,
        error="Task failed",
    )
    
    metrics = evaluator.get_agent_metrics("planner")
    assert metrics["total_tasks"] == 1
    assert metrics["failed_tasks"] == 1
    assert metrics["success_rate"] == 0.0


def test_evaluator_multiple_tasks():
    evaluator = AgentEvaluator()
    
    evaluator.record_task("t1", "planner", "session_1", True, 1000.0)
    evaluator.record_task("t2", "planner", "session_1", True, 2000.0)
    evaluator.record_task("t3", "planner", "session_1", False, 500.0)
    
    metrics = evaluator.get_agent_metrics("planner")
    assert metrics["total_tasks"] == 3
    assert metrics["successful_tasks"] == 2
    assert metrics["failed_tasks"] == 1
    assert 0.66 < metrics["success_rate"] < 0.68
    assert metrics["avg_duration_ms"] == pytest.approx(1166.67, rel=0.01)


def test_evaluator_record_session():
    evaluator = AgentEvaluator()
    
    evaluator.record_session(
        session_id="session_1",
        goal="Test goal",
        success=True,
        duration_ms=5000.0,
        total_tasks=5,
        completed_tasks=4,
        failed_tasks=1,
    )
    
    evaluation = evaluator.get_session_evaluation("session_1")
    assert evaluation["session_id"] == "session_1"
    assert evaluation["success"] is True
    assert evaluation["total_tasks"] == 5
    assert evaluation["completed_tasks"] == 4
    assert evaluation["completion_rate"] == 0.8


def test_evaluator_get_task_evaluations():
    evaluator = AgentEvaluator()
    
    evaluator.record_task("t1", "planner", "session_1", True, 1000.0)
    evaluator.record_task("t2", "research", "session_1", True, 2000.0)
    evaluator.record_task("t3", "planner", "session_2", False, 500.0)
    
    all_tasks = evaluator.get_task_evaluations()
    assert len(all_tasks) == 3
    
    session_1_tasks = evaluator.get_task_evaluations(session_id="session_1")
    assert len(session_1_tasks) == 2
    
    planner_tasks = evaluator.get_task_evaluations(agent_name="planner")
    assert len(planner_tasks) == 2


def test_evaluator_get_summary():
    evaluator = AgentEvaluator()
    
    evaluator.record_task("t1", "planner", "session_1", True, 1000.0)
    evaluator.record_task("t2", "research", "session_1", True, 2000.0)
    evaluator.record_task("t3", "planner", "session_1", False, 500.0)
    
    evaluator.record_session(
        session_id="session_1",
        goal="Test",
        success=True,
        duration_ms=5000.0,
        total_tasks=3,
        completed_tasks=2,
        failed_tasks=1,
    )
    
    summary = evaluator.get_summary()
    assert summary["total_tasks_evaluated"] == 3
    assert summary["successful_tasks"] == 2
    assert summary["failed_tasks"] == 1
    assert summary["overall_success_rate"] == pytest.approx(2/3)
    assert summary["total_sessions"] == 1
    assert summary["successful_sessions"] == 1
    assert summary["agents_evaluated"] == 2


def test_evaluator_leaderboard():
    evaluator = AgentEvaluator()
    
    evaluator.record_task("t1", "planner", "session_1", True, 1000.0)
    evaluator.record_task("t2", "planner", "session_2", True, 1000.0)
    evaluator.record_task("t3", "research", "session_1", False, 1000.0)
    
    leaderboard = evaluator.get_leaderboard()
    assert len(leaderboard) == 2
    assert leaderboard[0]["agent_name"] == "planner"
    assert leaderboard[0]["success_rate"] == 1.0


def test_evaluator_clear():
    evaluator = AgentEvaluator()
    
    evaluator.record_task("t1", "planner", "session_1", True, 1000.0)
    evaluator.record_session("session_1", "Goal", True, 1000.0, 1, 1, 0)
    
    evaluator.clear()
    
    assert evaluator.get_agent_metrics() == {}
    assert evaluator.get_session_evaluation("session_1") is None


def test_agent_metrics_tool_success_rate():
    evaluator = AgentEvaluator()
    
    evaluator.record_task(
        task_id="t1",
        agent_name="coding",
        session_id="session_1",
        success=True,
        duration_ms=1000.0,
        tools_used=5,
        tools_succeeded=4,
    )
    
    metrics = evaluator.get_agent_metrics("coding")
    assert metrics["total_tools_used"] == 5
    assert metrics["total_tools_succeeded"] == 4
    assert metrics["tool_success_rate"] == 0.8
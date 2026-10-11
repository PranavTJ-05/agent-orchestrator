import pytest
from src.orchestrator.core.task import Plan, Task, TaskStatus
from src.orchestrator.core.state import ExecutionState


class TestTask:
    def test_task_defaults(self) -> None:
        t = Task(id="t1", description="test task")
        assert t.status == TaskStatus.PENDING
        assert t.deps == []
        assert t.result is None
        assert t.error is None

    def test_task_with_deps(self) -> None:
        t = Task(id="t3", description="dependent", deps=["t1", "t2"])
        assert "t1" in t.deps
        assert "t2" in t.deps


class TestPlan:
    def test_topological_waves_simple(self) -> None:
        plan = Plan(
            goal="test",
            tasks=[
                Task(id="t1", description="first", deps=[]),
                Task(id="t2", description="second", deps=["t1"]),
                Task(id="t3", description="third", deps=["t2"]),
            ],
        )
        waves = plan.topological_waves()
        assert len(waves) == 3
        assert waves[0][0].id == "t1"
        assert waves[1][0].id == "t2"
        assert waves[2][0].id == "t3"

    def test_topological_waves_parallel(self) -> None:
        plan = Plan(
            goal="test",
            tasks=[
                Task(id="t1", description="A", deps=[]),
                Task(id="t2", description="B", deps=[]),
                Task(id="t3", description="C", deps=["t1", "t2"]),
            ],
        )
        waves = plan.topological_waves()
        assert len(waves) == 2
        assert len(waves[0]) == 2  # t1 and t2 in parallel
        assert len(waves[1]) == 1  # t3 depends on both


class TestExecutionState:
    def test_state_lifecycle(self) -> None:
        state = ExecutionState(session_id="s1", goal="test")
        t1 = Task(id="t1", description="first")
        state.add_task(t1)

        assert state.current_task is not None
        assert state.current_task.id == "t1"
        assert not state.is_complete

        state.update_task("t1", status=TaskStatus.COMPLETED, result="done")
        assert state.is_complete
        assert len(state.completed_tasks) == 1

    def test_current_task_none_when_empty(self) -> None:
        state = ExecutionState(session_id="s1", goal="test")
        assert state.current_task is None

from __future__ import annotations

from typing import Any

from ..core.tool import Tool


class DelegateTaskTool(Tool):
    """Tool that allows agents to delegate sub-tasks to other agents.
    
    This must be initialized with a reference to the orchestrator's agent registry
    and a way to execute tasks on other agents.
    """

    def __init__(self, orchestrator: Any | None = None) -> None:
        super().__init__(
            name="delegate_task",
            description="Delegate a sub-task to another agent. Use this when you need specialized work done by another agent (e.g., code, research, finance, critic, reviewer). The other agent will execute the task and return results.",
        )
        self._orchestrator = orchestrator

    def set_orchestrator(self, orchestrator: Any) -> None:
        """Set the orchestrator reference (called during initialization)."""
        self._orchestrator = orchestrator

    async def execute(
        self,
        agent_name: str,
        task_description: str,
    ) -> str:
        """Delegate a task to another agent.

        Args:
            agent_name: Name of the agent to delegate to. Options: research, finance, coding, critic, reviewer, planner, synthesizer
            task_description: Clear description of the task to be executed by the target agent
        """
        if not self._orchestrator:
            return "Error: DelegateTaskTool not connected to orchestrator."

        if agent_name not in self._orchestrator._agents:
            available = list(self._orchestrator._agents.keys())
            return f"Error: Agent '{agent_name}' not found. Available agents: {available}"

        target_agent = self._orchestrator._agents[agent_name]

        try:
            from ..core.task import TaskNode, TaskStatus
            task = TaskNode(
                id=f"delegated_{id(task_description)}",
                description=task_description,
                agent=agent_name,
                deps=[],
                status=TaskStatus.PENDING,
            )

            from ..core.state import ExecutionState
            state = ExecutionState(session_id="delegation", goal=task_description)
            state.add_task(task)
            state.update_task(task.id, status=TaskStatus.RUNNING, agent=agent_name)

            result = await target_agent.run(task=task, state=state)

            state.update_task(task.id, status=TaskStatus.COMPLETED, result=result)
            return f"Agent '{agent_name}' completed the task:\n\n{result}"

        except Exception as e:
            return f"Error delegating to agent '{agent_name}': {str(e)}"

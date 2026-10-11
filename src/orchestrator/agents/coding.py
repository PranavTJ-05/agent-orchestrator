from __future__ import annotations

import json
from typing import Any

from ..core.agent import BaseAgent
from ..core.state import ExecutionState
from ..llm.base import LLM
from ..sandbox import SandboxTool
from ..tools import (
    DatabaseTool,
    DelegateTaskTool,
    EditFileTool,
    GitHubTool,
    ListDirectoryTool,
    PythonExecutionTool,
    ReadFileTool,
    WriteFileTool,
)


class CodingAgent(BaseAgent):
    MAX_RETRIES = 3

    def __init__(self, llm: LLM, name: str = "coding", description: str = "Writes, runs, and debugs code using secure sandbox execution and file operation tools. Can also interact with GitHub, databases, and delegate tasks to other agents.") -> None:
        super().__init__(
            name=name,
            description=description,
            tools=[
                PythonExecutionTool(),
                SandboxTool(),
                ReadFileTool(),
                WriteFileTool(),
                EditFileTool(),
                ListDirectoryTool(),
                GitHubTool(),
                DatabaseTool(),
                DelegateTaskTool(),
            ],
        )
        self._llm = llm

    async def run(self, task: Any, state: ExecutionState | None = None) -> str:
        """Execute a coding task using LLM-driven tool calling with retry logic."""
        query = getattr(task, 'description', str(task))
        tools_schema = [tool.to_llm_tool() for tool in self.tools]

        system_prompt = """You are a coding agent with access to a secure sandbox for code execution.

You have these tools:
- sandbox_execute / python_execute: Run Python code securely in a sandbox. Use this for calculations, data analysis, and running scripts.
- read_file: Read the contents of a file
- write_file: Write content to a file  
- edit_file: Edit a file by replacing specific text
- list_directory: List contents of a directory
- github: Interact with GitHub repositories
- database: Execute SQL queries
- delegate_task: Delegate sub-tasks to other agents

When code fails with an error:
1. Read the error message carefully
2. Fix the code based on the error
3. Retry execution

Given a coding task, use tools to accomplish the goal. You may use multiple tools sequentially."""

        for attempt in range(self.MAX_RETRIES):
            content, tool_calls = await self._llm.generate(
                system_prompt=system_prompt,
                messages=[{"role": "user", "content": query}],
                tools=tools_schema,
                tool_choice="auto",
            )

            if tool_calls:
                results = []
                tool_execution_errors = []

                for tool_call in tool_calls:
                    if tool_call["type"] != "function":
                        continue
                    fn_name = tool_call["function"]["name"]
                    args = json.loads(tool_call["function"]["arguments"])
                    tool = next((t for t in self.tools if t.name == fn_name), None)
                    if not tool:
                        results.append(f"Tool not found: {fn_name}")
                        continue
                    try:
                        result = await tool.execute(**args)
                        results.append(f"{fn_name}:\n{result}")
                    except Exception as e:
                        error_msg = f"Tool {fn_name} failed: {e}"
                        results.append(error_msg)
                        tool_execution_errors.append(error_msg)

                if tool_execution_errors and attempt < self.MAX_RETRIES - 1:
                    query = f"Previous attempt failed with errors:\n" + "\n".join(tool_execution_errors) + f"\n\nOriginal task: {query}\n\nFix the errors and retry."
                    continue

                context = f"Task: {query}\n\nTool results:\n" + "\n\n".join(results)
                synthesis_prompt = """Based on the tool results above, provide a complete answer.
                Include the code you wrote, the output from execution, and any analysis."""
                final_content, _ = await self._llm.generate(
                    system_prompt=synthesis_prompt,
                    messages=[{"role": "user", "content": context}],
                )
                return final_content
            else:
                return content

        return content

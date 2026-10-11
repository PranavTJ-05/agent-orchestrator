# AI Agent Orchestrator

A sophisticated multi-agent system that coordinates multiple AI agents, tools, and workflows to accomplish complex tasks.

## Overview

Instead of relying on a single LLM to handle everything, the orchestrator:
- Understands user goals
- Breaks them into subtasks
- Chooses the best agent/tool for each task
- Tracks execution state
- Handles failures and retries
- Aggregates results
- Returns final responses

## Features Implemented

### ✅ Core Architecture
- **Agent Registry**: Dynamic registration and discovery of agents
- **Planner Agent**: Decomposes goals into task plans with dependencies
- **Router Agent**: Selects optimal agents for each task
- **Workflow Engine**: Supports sequential, parallel, and dependency-based execution
- **Memory System**: Short-term storage + ChromaDB vector database for long-term memory
- **State Management**: Tracks execution state, completed/failed tasks
- **Observability**: OpenTelemetry integration and structured logging

### ✅ Tool System (NEW)
- **Web Search Tool**: keyless DuckDuckGo search with a Wikipedia fallback
- **Stock Quote Tool**: real prices, ranges and headlines from Yahoo Finance
- **File Operations**: Read, write, edit, and list directory contents
- **Code Execution**: Safe Python code execution with restricted operations
- **Tool-Agent Integration**: Agents can now actually use tools to accomplish tasks

### ✅ Built-in Agents
- **PlannerAgent**: Creates execution plans from user goals
- **RouterAgent**: Routes tasks to appropriate agents
- **SynthesizerAgent**: Combines results into final coherent responses
- **ResearchAgent**: Performs web research using search tools
- **FinanceAgent**: Analyzes financial data and stock information
- **CodingAgent**: Writes, runs, and debugs code using Python execution and file operation tools
- **CriticAgent**: Reviews and critiques outputs from other agents, identifies flaws and suggests improvements
- **ReviewerAgent**: Performs final validation on outputs, checking completeness, correctness, and consistency

### ✅ Multi-LLM Support
- **OpenAI**: GPT models
- **Anthropic**: Claude models  
- **Groq**: free tier, OpenAI-compatible (`openai/gpt-oss-120b`)
- **Gemini**: free tier via Google's OpenAI-compatible endpoint
- **HuggingFace** and **OpenRouter**: open models

## Installation

```bash
# Clone the repository
git clone <repository-url>
cd agent-orchestrator

# Install dependencies
python3 -m venv .venv && .venv/bin/pip install -e .

# Set up environment variables (copy from .env.example)
cp .env.example .env
# Edit .env to add your API keys
```

## Quick start with a free Groq key

1. Create a key at https://console.groq.com/keys and put it in `.env`:
   ```
   GROQ_API_KEY=gsk_...
   DEFAULT_LLM_PROVIDER=groq
   DEFAULT_LLM_MODEL=openai/gpt-oss-120b
   MEMORY_EMBEDDING=hash   # skips Chroma's 79MB embedding model download
   ```
2. Run a goal: `orchestrator run "What is the current stock price of Tesla (TSLA)?"`
3. Optional dashboard: `orchestrator serve --port 8003` and, in another terminal, `cd dashboard && npm ci && npm run dev` (http://localhost:3000).

Only `GROQ_API_KEY` is required. `GEMINI_API_KEY`, `E2B_API_KEY` and `GITHUB_TOKEN` are optional.

## Token budget

Free tiers cap tokens per minute, so the pipeline is built to stay small:
plans are limited to 4 tasks, planner agent names map straight to agents (no routing call),
the synthesizer truncates each task result, and `LLM_MAX_TOKENS` (default 1500) caps replies.
Every `orchestrator run` ends with a line showing total tokens, LLM calls and the largest prompt.
Set `LOG_LEVEL=INFO` for the full event log.

## Usage

### Command Line Interface

```bash
# Run a single goal
orchestrator run --provider groq --model openai/gpt-oss-120b "Analyze Tesla stock and create a report"

# Interactive mode
orchestrator interactive --provider groq --model openai/gpt-oss-120b

# Start the API server
orchestrator serve --provider groq --port 8003
```

### API Endpoints

Once the server is running (`orchestrator serve`):

- **GET /** - API information and endpoint documentation
- **POST /run** - Execute a goal: `{"goal": "your task here"}`
- **GET /status/{session_id}** - Get session results
- **POST /agents/register** - Register custom agents
- **GET /agents** - List registered agents
- **GET /health** - Health check

## Example Workflow

For the goal: `"Analyze Tesla stock, find recent news, compare competitors, and create an investment report."`

1. **Planner Agent** creates execution plan:
   - Task 1: Research Tesla company info
   - Task 2: Gather latest Tesla news  
   - Task 3: Analyze Tesla stock metrics
   - Task 4: Research competitor companies (Ford, GM, etc.)
   - Task 5: Write Python script to compare financial ratios
   - Task 6: Review the financial analysis for accuracy
   - Task 7: Final validation of the investment report
   - Task 8: Generate investment report

2. **Router Agent** assigns tasks:
   - Research tasks → ResearchAgent (with web search tool)
   - Finance tasks → FinanceAgent (with web search tool)
   - Code tasks → CodingAgent (with Python + file tools)
   - Review tasks → CriticAgent (identifies flaws, suggests improvements)
   - Validation tasks → ReviewerAgent (final approval gate)
   - Report generation → SynthesizerAgent

3. **Agents execute** using their tools:
   - ResearchAgent searches web for company info and news
   - FinanceAgent searches for financial data and stock metrics
   - CodingAgent writes and runs Python analysis scripts
   - CriticAgent reviews outputs for accuracy and completeness
   - ReviewerAgent performs final validation before output

4. **Synthesizer Agent** combines all results into final report

5. **State Management** tracks progress and handles failures

## Tool Examples

### File Operations
```python
# Read a file
read_tool = ReadFileTool()
content = await read_tool.execute("config.txt")

# Write a file  
write_tool = WriteFileTool()
result = await write_tool.execute("output.txt", "Hello World")

# Edit a file
edit_tool = EditFileTool()
result = await edit_tool.execute("config.txt", "old_value", "new_value")

# List directory
list_tool = ListDirectoryTool()
files = await list_tool.execute("./")
```

### Code Execution
```python
# Execute Python code
python_tool = PythonExecutionTool()
result = await python_tool.execute("""
import math
print(f"Square root of 16: {math.sqrt(16)}")
for i in range(5):
    print(f"Number: {i}, Square: {i**2}")
""")
```

### Web Search
```python
# Search the web
search_tool = WebSearchTool()
results = await search_tool.execute("latest AI developments 2024", num_results=5)
# Returns list of dicts with title, snippet, url
```

## Architecture Details

### Agent Communication Flow
```
User Goal
    │
    ▼
┌─────────────┐
│  Planner    │◄────────────┐
└─────────────┘             │
    │                       ▼
    ▼              ┌──────────────┐
┌─────────────┐    │  Router      │
│ Task 1      │───►│ (Agent       │
│ [Research]  │    │  Selection)  │
└─────────────┘    └──────────────┘
    │                       ▲
    ▼                       │
┌─────────────┐             │
│ Research    │◄────────────┘
│ Agent       │
│ (uses web   │
│ search tool)│
└─────────────┘
    │
    ▼
┌─────────────┐
│  Result 1   │
└─────────────┘
    │
    ▼
┌─────────────┐
│  Synthesizer│◄───────┐
│  Agent      │        │
└─────────────┘        │
    │                  ▼
    ▼           ┌─────────────┐
┌─────────────┐│ Research    │
│ Final Result│◄────────────│
└─────────────┘│ Agent       │
               └─────────────┘
```

## Extending the System

### Adding New Tools
1. Create a new class inheriting from `Tool` in `src/orchestrator/tools/`
2. Implement the `execute` method
3. Add the tool to `src/orchestrator/tools/__init__.py`
4. Add the tool to any agent's `tools` list

### Adding New Agents
1. Create a new class inheriting from `BaseAgent` in `src/orchestrator/agents/`
2. Implement the `run` method
3. Add the agent to `src/orchestrator/agents/__init__.py`
4. Register the agent in the orchestrator (automatic for built-ins)

### Adding New LLM Providers
1. Create a new class inheriting from `LLM` in `src/orchestrator/llm/`
2. Implement the `generate` method
3. Add the provider to `src/orchestrator/llm/__init__.py`
4. Add the provider to the `create_llm` factory function

## Testing

Run the test suite:
```bash
python -m pytest tests/ -v
```

## License

MIT

## Acknowledgments

Built with:
- FastAPI for the API server
- Pydantic for data validation
- Rich for beautiful CLI output
- ChromaDB for vector storage
- OpenTelemetry for observability
- HuggingFace Hub for LLM access

---

Built by PranavTJ-05

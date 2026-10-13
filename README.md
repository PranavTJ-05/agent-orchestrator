# AI Agent Orchestrator

A multi-agent system that turns one goal into a plan, hands each step to the right specialist agent, and combines the results into a single answer. It also includes **MCP Studio**: connect any [MCP](https://modelcontextprotocol.io) server (local, remote or OAuth) and the agents will pick the right tool and call it, with your approval for anything risky.

> **Demo video: coming soon.** A walkthrough of the full workflow (ask, plan, pick a tool, approve, execute) will be added here.

**Contents:** [What it does](#what-it-does) · [Quick start](#quick-start) · [How it works](#how-it-works) · [MCP Studio](#mcp-studio) · [Usage](#usage) · [Extending](#extending-the-system) · [Testing](#testing)

---

## What it does

Instead of asking one LLM to do everything, the orchestrator:

1. **Plans**: breaks your goal into at most 4 tasks with dependencies.
2. **Routes**: assigns each task to the best agent.
3. **Executes**: runs independent tasks in parallel, passing earlier results to later ones.
4. **Recovers**: retries failures and tracks state.
5. **Synthesizes**: merges everything into one final answer.

| Area | What you get |
| --- | --- |
| Agents | Planner, Router, Research, Finance, Coding, Critic, Reviewer, Synthesizer, MCP |
| Tools | Web search (DuckDuckGo, Wikipedia fallback), stock quotes (Yahoo Finance), file operations, sandboxed Python |
| LLMs | OpenAI, Anthropic, Groq (free), Gemini (free), HuggingFace, OpenRouter |
| Memory | Short-term state plus ChromaDB long-term memory |
| MCP Studio | Any number of MCP servers, on-device tool picking, approvals, live activity feed |
| Observability | Structured logging and OpenTelemetry |
| Dashboard | Apple-style React UI, light and dark following your system |

## Quick start

You only need a free Groq key.

```bash
git clone https://github.com/PranavTJ-05/agent-orchestrator.git
cd agent-orchestrator
python3 -m venv .venv && .venv/bin/pip install -e .
cp .env.example .env
```

Create a key at <https://console.groq.com/keys> and set these in `.env`:

```
GROQ_API_KEY=gsk_...
DEFAULT_LLM_PROVIDER=groq
DEFAULT_LLM_MODEL=openai/gpt-oss-120b
MEMORY_EMBEDDING=hash   # skips Chroma's 79MB embedding model download
```

Then run a goal:

```bash
orchestrator run "What is the current stock price of Tesla (TSLA)?"
```

Optional dashboard (http://localhost:3000):

```bash
orchestrator serve --port 8003          # terminal 1
cd dashboard && npm ci && npm run dev   # terminal 2
```

`GEMINI_API_KEY`, `E2B_API_KEY` and `GITHUB_TOKEN` are optional.

## How it works

```
Goal
 │
 ▼
Planner ──► task graph (max 4 tasks, with dependencies)
 │
 ▼
Router ──► picks an agent per task
 │
 ▼
Agents run in waves (independent tasks in parallel)
 ├─ Research   web search
 ├─ Finance    stock quotes + search
 ├─ Coding     Python + file tools
 ├─ Critic / Reviewer   check the work
 └─ MCP        tools from your connected MCP servers
 │
 ▼
Synthesizer ──► final answer
```

**Example.** For *"Analyze Tesla stock, find recent news and write a report"*: the planner creates research, finance and write tasks; the router sends them to the Research, Finance and Synthesizer agents; the first two run in parallel with real search and Yahoo Finance data; the synthesizer writes the report from those results.

### Token budget

Free tiers cap tokens per minute, so the pipeline is built to stay small: plans are limited to 4 tasks, planner agent names map straight to agents (no routing call), the synthesizer truncates each result, and `LLM_MAX_TOKENS` (default 1500) caps replies. Every `orchestrator run` ends with total tokens, LLM calls and the largest prompt. Set `LOG_LEVEL=INFO` for the full event log.

## MCP Studio

Open the dashboard, go to **Studio**, and add a server:

- **Local command**: for example `npx -y @modelcontextprotocol/server-filesystem ~/Documents`, with optional environment variables.
- **Remote HTTP / SSE**: a URL with optional headers, or **Sign in with OAuth** for servers that log you in through the browser.

Servers are saved to `.studio/servers.json` (owner-only permissions, git-ignored) and reconnect on restart.

### The workflow

```
Ask  ──►  Plan  ──►  Pick tool  ──►  Approve  ──►  Execute  ──►  Answer
          (LLM)      (Jev, local)    (you, if      (MCP call,
                                      risky)        validated)
```

1. **Plan.** If a task names a connected server (for example "in Eraser"), it goes to the MCP agent.
2. **Pick.** A small on-device decision model ([Jev-Style 0.8B v3](https://huggingface.co/chaoliangUNSW/Jev-Style-0.8B-Decision-v3-GGUF), community model, CPU only) ranks every connected tool. With many tools it chooses a group first, then the tool. Only the top few tool schemas go to the LLM, so token cost stays flat however many servers you connect. If the model is not installed, keyword matching is used instead.
3. **Look up.** If the shortlist is missing something (such as a file ID), the LLM can call `find_tools` to pull in more tools. When the pick is uncertain it also sees the names of the other tools.
4. **Approve.** See below.
5. **Execute.** Arguments are checked against the server's JSON schema, calls time out after 60 seconds, and identical write calls are never repeated, since a timed-out write may still have happened.

The **Tool picker** panel in Studio shows the ranking and latency.

### Install the picker model

```bash
pip install llama-cpp-python --prefer-binary --only-binary=:all: \
  --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu   # prebuilt CPU wheel, no compiler needed
mkdir -p models && curl -L -o models/Jev-Style-0.8B-Decision-v3-Q4_K_M.gguf \
  https://huggingface.co/chaoliangUNSW/Jev-Style-0.8B-Decision-v3-GGUF/resolve/main/Jev-Style-0.8B-Decision-v3-Q4_K_M.gguf
```

On a laptop CPU it runs at about 140 tokens/s. A pick takes 1 to 3 seconds with a few tools and 5 to 14 seconds on a 42-tool server. On a small hand-written benchmark of 20 tools it chose the right one 20 out of 20 times. Treat that as a smoke test, not a rigorous evaluation.

### Approvals

Each server has a policy:

| Policy | Behaviour |
| --- | --- |
| **Smart** (default) | Read-only tools run automatically. Writes, deletes and tools without a read-only hint ask first. |
| **Always ask** | Every call asks. |
| **Allow all** | Nothing asks. |
| **Block** | Nothing runs. |

Prompts appear in the dashboard; `orchestrator run` asks in the terminal. Unanswered requests are denied after 2 minutes.

### Tested with a real server

Connected to [Eraser](https://app.eraser.io/api/mcp) over OAuth (42 tools). Asked to draw a frontend, backend and database diagram, the agent picked Eraser's tools, asked for approval, and created the diagram. Results vary between runs because the LLM's choices vary, and a run takes roughly 30 to 70 seconds on CPU. Files created through some MCP servers may be shared by default, so check your account settings.

### Security

Adding a local server runs a command on your machine, so the API is locked down: it binds to `127.0.0.1`, accepts only the dashboard's origin, checks the `Host` header (DNS rebinding), and requires JSON bodies on state-changing routes so other websites cannot drive it. **Do not expose port 8003 to a network.** Set `STUDIO_ALLOWED_ORIGINS` and `STUDIO_ALLOWED_HOSTS` only if you know you need to.

`orchestrator run` starts the servers configured in Studio automatically (`--no-mcp` to skip).

## Usage

### Command line

```bash
orchestrator run --provider groq --model openai/gpt-oss-120b "Analyze Tesla stock and create a report"
orchestrator interactive --provider groq --model openai/gpt-oss-120b
orchestrator serve --provider groq --port 8003
```

### API

With `orchestrator serve` running:

| Endpoint | Purpose |
| --- | --- |
| `POST /run` | Execute a goal: `{"goal": "your task here"}` |
| `GET /status/{session_id}` | Session results |
| `GET /agents`, `POST /agents/register` | List or register agents |
| `GET /health` | Health check |
| `/studio/*` | MCP Studio: servers, tools, tool picker, approvals, live events |

### Tools in code

```python
content = await ReadFileTool().execute("config.txt")
await WriteFileTool().execute("output.txt", "Hello World")
await EditFileTool().execute("config.txt", "old_value", "new_value")
files = await ListDirectoryTool().execute("./")

result = await PythonExecutionTool().execute("print(2 + 2)")
results = await WebSearchTool().execute("latest AI developments", num_results=5)  # title, snippet, url
```

## Extending the system

- **New tool:** subclass `Tool` in `src/orchestrator/tools/`, implement `execute`, export it in `tools/__init__.py`, and add it to an agent's `tools` list.
- **New agent:** subclass `BaseAgent` in `src/orchestrator/agents/`, implement `run`, and export it in `agents/__init__.py`.
- **New LLM provider:** subclass `LLM` in `src/orchestrator/llm/`, implement `generate`, and add it to the `create_llm` factory.

## Testing

```bash
python -m pytest tests/ -v
```

## License

MIT

## Acknowledgments

FastAPI, Pydantic, Rich, ChromaDB, OpenTelemetry, the official MCP Python SDK, llama.cpp, React and Vite.

---

Built by PranavTJ-05

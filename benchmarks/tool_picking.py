"""Smoke test for the Jev tool picker: 20 tools across 10 servers, 20 paraphrased tasks.

Run:  python benchmarks/tool_picking.py
Both the catalogue and the tasks are hand-written (small, not a rigorous evaluation).
The tasks are phrased the way people talk, with little word overlap with tool names,
which is where keyword matching fails and a decision model should not.
"""
import asyncio
import re
import statistics
import time

from orchestrator.studio import ToolInfo, ToolPicker

TOOLS = {
    "filesystem.read_file": "Read the contents of a file from the local disk",
    "filesystem.write_file": "Create or overwrite a file on the local disk",
    "filesystem.list_directory": "List files and folders inside a directory",
    "github.create_issue": "Open a new issue in a GitHub repository",
    "github.search_code": "Search source code across GitHub repositories",
    "github.create_pull_request": "Open a pull request on GitHub from a branch",
    "fetch.fetch_url": "Download a web page by URL and return its text",
    "postgres.query": "Run a read-only SQL query against a Postgres database",
    "slack.post_message": "Send a message to a Slack channel",
    "slack.search_messages": "Search past Slack conversations",
    "calendar.create_event": "Schedule a meeting or event on the calendar",
    "calendar.list_events": "Show upcoming events and meetings on the calendar",
    "stocks.get_quote": "Get the current price of a stock ticker",
    "email.send_email": "Send an email to a recipient",
    "email.search_inbox": "Search emails in the inbox",
    "weather.get_forecast": "Get the weather forecast for a city",
    "notion.create_page": "Create a new page in a Notion workspace",
    "jira.create_ticket": "Create a Jira ticket for a task or bug",
    "maps.directions": "Get driving or walking directions between two places",
    "translate.translate_text": "Translate text from one language to another",
}
TASKS = [
    ("Show me what's inside config.yaml", "filesystem.read_file"),
    ("Save these meeting notes into notes/today.md", "filesystem.write_file"),
    ("What files are in the src folder?", "filesystem.list_directory"),
    ("File a bug report on our repo about the login crash", "github.create_issue"),
    ("Find where parse_config is defined across our repos", "github.search_code"),
    ("Raise a PR from the feature/auth branch", "github.create_pull_request"),
    ("Read the article at https://example.com/blog/post", "fetch.fetch_url"),
    ("How many users signed up last week? check the database", "postgres.query"),
    ("Tell the team in #general that the deploy is done", "slack.post_message"),
    ("What did we discuss about pricing in Slack last month?", "slack.search_messages"),
    ("Set up a call with Maria tomorrow at 3pm", "calendar.create_event"),
    ("What's on my schedule this afternoon?", "calendar.list_events"),
    ("What is Tesla trading at right now?", "stocks.get_quote"),
    ("Email the invoice to accounts@acme.com", "email.send_email"),
    ("Find the email from my landlord about the lease", "email.search_inbox"),
    ("Do I need an umbrella in Berlin tomorrow?", "weather.get_forecast"),
    ("Start a project wiki page called Q4 roadmap", "notion.create_page"),
    ("Track this checkout failure as a ticket for the backend team", "jira.create_ticket"),
    ("How do I get from Heathrow to King's Cross?", "maps.directions"),
    ("Say 'where is the train station' in Japanese", "translate.translate_text"),
]


def keyword_rank(task: str, tools: list[ToolInfo]) -> list[str]:
    words = lambda s: set(re.findall(r"[a-z]+", s.lower().replace("_", " ")))
    q = words(task)
    return [f"{t.server_id}.{t.name}" for t in sorted(
        tools, key=lambda t: -len(q & words(f"{t.name} {t.description}")))]


async def main() -> None:
    tools = [ToolInfo(server_id=q.split(".")[0], name=q.split(".")[1], qualified=q.replace(".", "__"),
                      description=d, input_schema={"type": "object", "properties": {}})
             for q, d in TOOLS.items()]
    picker = ToolPicker()
    if not picker.scorer.available():
        raise SystemExit("Jev model not found: see the MCP Studio section of the README")
    picker.scorer.warm()
    top1 = top3 = kw1 = 0
    latencies: list[float] = []
    for task, gold in TASKS:
        started = time.time()
        result = await picker.pick(task, tools, k=3)
        latencies.append(time.time() - started)
        names = [f"{p.server_id}.{p.name}" for p in result.tools]
        top1 += names[0] == gold
        top3 += gold in names
        kw1 += keyword_rank(task, tools)[0] == gold
        if names[0] != gold:
            print(f"MISS {task!r}: picked {names[0]} (confidence {result.confidence}), expected {gold}")
    n = len(TASKS)
    print(f"Jev picker ({result.method}), {len(tools)} tools / 10 servers")
    print(f"  top-1 {top1}/{n}   top-3 {top3}/{n}   keyword baseline top-1 {kw1}/{n}")
    print(f"  latency mean {statistics.mean(latencies):.1f}s, max {max(latencies):.1f}s per pick")


if __name__ == "__main__":
    asyncio.run(main())

from __future__ import annotations

import asyncio
from typing import Optional

from dotenv import load_dotenv
import typer

load_dotenv()  # Load .env file for API keys
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table

from .engine.orchestrator import AgentOrchestrator
from .llm import LLMConfig, create_llm
from .observability.logger import setup_logging

app = typer.Typer(
    name="orchestrator",
    help="AI Agent Orchestrator — coordinate multiple agents to accomplish complex tasks",
)
console = Console()


@app.command()
def run(
    goal: str,
    model: str = "Qwen/Qwen2.5-7B-Instruct",
    provider: str = "huggingface",
    session: Optional[str] = None,
    dag: bool = typer.Option(False, "--dag", help="Show DAG before executing"),
    mcp: bool = typer.Option(True, "--mcp/--no-mcp", help="Use MCP servers configured in Studio"),
) -> None:
    """Execute a goal through the orchestrator."""
    setup_logging()

    if dag:
        console.print("[bold cyan]Generating DAG...[/bold cyan]")
        dag_llm = create_llm(LLMConfig(provider=provider, model=model))
        dag_orchestrator = AgentOrchestrator(llm=dag_llm)
        dag_data = dag_orchestrator.get_dag(goal)
        _print_dag(dag_data)
        response = console.input("\n[yellow]Continue with execution? (y/n): [/yellow]")
        if response.lower() != "y":
            console.print("[bold red]Execution cancelled.[/bold red]")
            return

    llm = create_llm(LLMConfig(provider=provider, model=model))
    result = asyncio.run(_execute(goal, llm, session, mcp))

    console.print(Panel(Markdown(result), title="[bold]Result", border_style="green"))
    usage = llm.get_usage()
    console.print(
        f"[dim]Tokens: {usage.total_tokens} total ({usage.prompt_tokens} prompt + "
        f"{usage.completion_tokens} completion) | {usage.calls} LLM calls | "
        f"largest prompt {usage.max_prompt_tokens}[/dim]"
    )


async def _execute(goal: str, llm, session: Optional[str], use_mcp: bool) -> str:
    """Run a goal, starting the Studio's MCP servers first when any are configured."""
    from .studio import StudioManager
    from .studio.store import ServerStore

    status = console.status("[bold green]Planning and executing...")
    studio = None
    if use_mcp:
        store = ServerStore()
        if any(spec.enabled for spec in store.load()):
            studio = StudioManager(store=store)

            async def ask(item) -> bool:
                status.stop()
                console.print(f"\n[bold yellow]Approval needed[/bold yellow]: {item.server_id}.{item.tool}"
                              f"{' (destructive)' if item.destructive else ''}\n  {item.summary}")
                answer = await asyncio.to_thread(input, "Allow this tool call? [y/N] ")
                status.start()
                return answer.strip().lower() in ("y", "yes")

            studio.approvals.handler = ask
            await studio.start()
            for _ in range(200):  # wait up to ~20s for servers to connect
                if all(st.status in ("connected", "error", "disabled", "needs_auth") for st in studio.states()):
                    break
                await asyncio.sleep(0.1)
            console.print(f"[dim]MCP: {len(studio.tools())} tools from "
                          f"{sum(st.status == 'connected' for st in studio.states())} server(s)[/dim]")
    orchestrator = AgentOrchestrator(llm=llm, studio=studio)
    status.start()
    try:
        return await orchestrator.execute(goal, session_id=session)
    finally:
        status.stop()
        if studio:
            await studio.stop()


@app.command()
def dag(
    goal: str,
    model: str = "Qwen/Qwen2.5-7B-Instruct",
    provider: str = "huggingface",
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Save DAG to file"),
    json: bool = typer.Option(False, "--json", help="Output as JSON"),
) -> None:
    """Show the DAG (task graph) for a goal without executing."""
    setup_logging()
    llm = create_llm(LLMConfig(provider=provider, model=model))
    orchestrator = AgentOrchestrator(llm=llm)

    console.print("[bold cyan]Generating DAG...[/bold cyan]")
    dag_data = orchestrator.get_dag(goal)

    if json:
        import json as json_module
        dag_json = json_module.dumps(dag_data, indent=2)
        if output:
            with open(output, 'w') as f:
                f.write(dag_json)
            console.print(f"[green]DAG saved to {output}[/green]")
        else:
            console.print(dag_json)
    else:
        _print_dag(dag_data)
        if output:
            import tempfile
            # Save as text
            with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
                _write_dag_text(dag_data, f)
            console.print(f"[green]DAG saved to {output}[/green]")


def _print_dag(dag_data: dict) -> None:
    """Print DAG in a formatted table."""
    from rich.tree import Tree
    from rich.jupyter import JupyterMixin
    
    # Print nodes table
    nodes_table = Table(title="DAG Nodes", show_header=True, header_style="bold magenta")
    nodes_table.add_column("ID", style="cyan")
    nodes_table.add_column("Description", style="white")
    nodes_table.add_column("Agent", style="green")
    nodes_table.add_column("Status", style="yellow")
    nodes_table.add_column("Requires Approval", style="red")

    for node in dag_data.get("nodes", []):
        nodes_table.add_row(
            node.get("id", ""),
            node.get("description", "")[:40],
            node.get("agent", "") or "-",
            node.get("status", ""),
            "⚠️ YES" if node.get("requires_approval") else "No",
        )

    console.print(nodes_table)

    # Print edges
    edges_table = Table(title="DAG Edges (Dependencies)", show_header=True, header_style="bold magenta")
    edges_table.add_column("From", style="cyan")
    edges_table.add_column("To", style="cyan")
    edges_table.add_column("Type", style="green")

    for edge in dag_data.get("edges", []):
        edges_table.add_row(
            edge.get("source", ""),
            edge.get("target", ""),
            edge.get("edge_type", ""),
        )

    if dag_data.get("edges"):
        console.print(edges_table)

    # Print as tree
    tree = Tree(f"📋 [bold cyan]Goal: {dag_data.get('goal', '')[:50]}...[/bold cyan]")
    
    # Group nodes by dependencies
    root_nodes = []
    node_map = {n.get("id"): n for n in dag_data.get("nodes", [])}
    
    for edge in dag_data.get("edges", []):
        source = edge.get("source")
        target = edge.get("target")
        if source and target:
            if source not in node_map:
                continue
            source_node = node_map[source]
            approval = " ⚠️" if source_node.get("requires_approval") else ""
            tree.add(f"📌 {source}{approval}")
    
    console.print(tree)


def _write_dag_text(dag_data: dict, file) -> None:
    """Write DAG as text to file."""
    file.write(f"Goal: {dag_data.get('goal', '')}\n\n")
    file.write("=" * 50 + "\n")
    file.write("NODES\n")
    file.write("=" * 50 + "\n\n")
    
    for node in dag_data.get("nodes", []):
        file.write(f"ID: {node.get('id', '')}\n")
        file.write(f"  Description: {node.get('description', '')}\n")
        file.write(f"  Agent: {node.get('agent', '')}\n")
        file.write(f"  Status: {node.get('status', '')}\n")
        file.write(f"  Requires Approval: {node.get('requires_approval', False)}\n")
        file.write("\n")
    
    file.write("=" * 50 + "\n")
    file.write("EDGES\n")
    file.write("=" * 50 + "\n\n")
    
    for edge in dag_data.get("edges", []):
        file.write(f"{edge.get('source', '')} -> {edge.get('target', '')} [{edge.get('edge_type', '')}]\n")


@app.command()
def serve(
    host: str = "127.0.0.1",
    port: int = 8000,
    model: str = "Qwen/Qwen2.5-7B-Instruct",
    provider: str = "mock",
) -> None:
    """Start the FastAPI server."""
    import uvicorn
    setup_logging()
    console.print(f"[bold green]Starting orchestrator API on {host}:{port}")
    console.print(f"[dim]LLM: {provider}/{model}")
    uvicorn.run(
        "orchestrator.api.server:app",
        host=host,
        port=port,
        reload=False,
    )


@app.command()
def interactive(
    model: str = "openrouter/auto",
    provider: str = "openrouter",
) -> None:
    """Interactive CLI session with the orchestrator."""
    setup_logging()
    llm = create_llm(LLMConfig(provider=provider, model=model))
    orchestrator = AgentOrchestrator(llm=llm)

    console.print("[bold cyan]AI Agent Orchestrator — Interactive Mode[/bold cyan]")
    console.print("[dim]Type 'exit' to quit, 'agents' to list registered agents[/dim]\n")

    while True:
        goal = typer.prompt("Goal", default="")
        if goal.lower() in ("exit", "quit"):
            break
        if goal.lower() == "agents":
            table = Table(title="Registered Agents")
            table.add_column("Name", style="cyan")
            table.add_column("Description")
            for name, agent in orchestrator._agents.items():
                table.add_row(name, agent.description)
            console.print(table)
            continue
        if not goal:
            continue

        with console.status("[bold green]Working...") as status:
            try:
                result = asyncio.run(orchestrator.execute(goal))
                console.print(Panel(Markdown(result), border_style="green"))
            except Exception as e:
                console.print(f"[bold red]Error:[/bold red] {e}")


if __name__ == "__main__":
    app()

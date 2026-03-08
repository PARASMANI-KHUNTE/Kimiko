"""Kimiko CLI — a beautiful terminal interface for the AI agent.

Commands:
    kimiko chat             Interactive chat session
    kimiko ask "question"   One-shot question
    kimiko memory           View stored facts and memories
    kimiko plugins          List loaded plugins
    kimiko status           Check system health
"""

from __future__ import annotations

import sys
from typing import Optional

import httpx
import typer
from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table
from rich.prompt import Prompt
from rich.text import Text
from rich import box

console = Console()
app = typer.Typer(
    name="kimiko",
    help="🏯 Kimiko AI — Your local intelligent assistant.",
    add_completion=False,
)

API_URL = "http://localhost:8000/v1"


def _get_headers() -> dict:
    return {"X-API-Key": "test-key-123", "Content-Type": "application/json"}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  STATUS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
@app.command()
def status():
    """Check if the Kimiko API is online."""
    try:
        with httpx.Client(timeout=5.0) as client:
            resp = client.get(f"{API_URL.replace('/v1','')}/health")
            if resp.status_code == 200:
                console.print(Panel(
                    "[bold green]✅ Kimiko is online[/bold green]",
                    title="System Status",
                    border_style="green",
                ))
            else:
                console.print(Panel(
                    f"[bold yellow]⚠️ Unexpected status: {resp.status_code}[/bold yellow]",
                    title="System Status",
                    border_style="yellow",
                ))
    except httpx.ConnectError:
        console.print(Panel(
            "[bold red]❌ Kimiko is offline[/bold red]\n\nRun: docker-compose up -d",
            title="System Status",
            border_style="red",
        ))


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  ASK (one-shot)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
@app.command()
def ask(
    question: str = typer.Argument(..., help="Your question for Kimiko."),
    model: str = typer.Option("qwen2.5", help="Model to use."),
):
    """Ask Kimiko a one-shot question."""
    console.print()
    console.print(f"[dim]→ Asking: {question}[/dim]")
    console.print()

    payload = {"message": question, "model": model}

    try:
        with httpx.Client(timeout=120.0, headers=_get_headers()) as client:
            resp = client.post(f"{API_URL}/chat", json=payload)

            if resp.status_code == 200:
                data = resp.json()
                answer = data.get("response", {}).get("content", "No response.")
                console.print(Panel(
                    Markdown(answer),
                    title="🏯 Kimiko",
                    border_style="cyan",
                    padding=(1, 2),
                ))
            else:
                console.print(f"[red]Error {resp.status_code}: {resp.text}[/red]")
    except httpx.ConnectError:
        console.print("[red]❌ Cannot connect to Kimiko. Is the API running?[/red]")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  CHAT (interactive session)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
@app.command()
def chat(
    model: str = typer.Option("qwen2.5", help="Model to use."),
    session: str = typer.Option("cli-session", help="Session ID for memory."),
):
    """Start an interactive chat session with Kimiko."""
    console.print(Panel(
        "[bold cyan]🏯 Kimiko Chat[/bold cyan]\n"
        "[dim]Type your message and press Enter. Type 'exit' or 'quit' to leave.[/dim]",
        border_style="cyan",
        box=box.DOUBLE,
    ))

    while True:
        try:
            user_input = Prompt.ask("\n[bold green]You[/bold green]")
        except (KeyboardInterrupt, EOFError):
            break

        if user_input.strip().lower() in ("exit", "quit", "bye"):
            console.print("\n[dim]👋 Goodbye![/dim]")
            break

        if not user_input.strip():
            continue

        payload = {
            "message": user_input,
            "model": model,
            "session_id": session,
        }

        try:
            with httpx.Client(timeout=120.0, headers=_get_headers()) as client:
                resp = client.post(f"{API_URL}/chat", json=payload)

                if resp.status_code == 200:
                    data = resp.json()
                    answer = data.get("response", {}).get("content", "...")
                    console.print()
                    console.print(Panel(
                        Markdown(answer),
                        title="🏯 Kimiko",
                        border_style="cyan",
                        padding=(1, 2),
                    ))
                else:
                    console.print(f"[red]Error {resp.status_code}[/red]")

        except httpx.ConnectError:
            console.print("[red]❌ Connection lost.[/red]")
            break


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  MEMORY
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
@app.command()
def memory(
    user_id: str = typer.Option("default", help="User ID to query facts for."),
):
    """View Kimiko's stored memories and facts."""
    console.print(Panel(
        "[bold]🧠 Kimiko Memory Explorer[/bold]",
        border_style="magenta",
    ))

    try:
        with httpx.Client(timeout=10.0, headers=_get_headers()) as client:
            resp = client.get(f"{API_URL}/memory/facts", params={"user_id": user_id})

            if resp.status_code == 200:
                facts = resp.json().get("facts", [])
                if not facts:
                    console.print("[dim]No facts stored yet. Start chatting![/dim]")
                    return

                table = Table(
                    title="Stored Facts",
                    box=box.ROUNDED,
                    border_style="magenta",
                )
                table.add_column("Category", style="cyan", width=15)
                table.add_column("Fact", style="white")
                table.add_column("Confidence", style="green", justify="center", width=12)

                for f in facts:
                    conf = f.get("confidence", 0)
                    conf_str = f"{conf:.0%}" if isinstance(conf, float) else str(conf)
                    table.add_row(
                        f.get("category", "—"),
                        f.get("fact", "—"),
                        conf_str,
                    )

                console.print(table)
            elif resp.status_code == 404:
                console.print("[dim]Memory API endpoint not found. Is the API up to date?[/dim]")
            else:
                console.print(f"[red]Error {resp.status_code}: {resp.text}[/red]")

    except httpx.ConnectError:
        console.print("[red]❌ Cannot connect to Kimiko.[/red]")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  PLUGINS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
@app.command()
def plugins():
    """List all loaded Kimiko plugins."""
    console.print(Panel(
        "[bold]🔌 Installed Plugins[/bold]",
        border_style="blue",
    ))

    try:
        with httpx.Client(timeout=10.0, headers=_get_headers()) as client:
            resp = client.get(f"{API_URL}/plugins")

            if resp.status_code == 200:
                plugin_list = resp.json().get("plugins", [])
                if not plugin_list:
                    console.print("[dim]No plugins installed.[/dim]")
                    return

                table = Table(box=box.ROUNDED, border_style="blue")
                table.add_column("Name", style="cyan bold")
                table.add_column("Version", style="green")
                table.add_column("Author", style="white")
                table.add_column("Capabilities", style="yellow")

                for p in plugin_list:
                    caps = ", ".join(p.get("capabilities", []))
                    table.add_row(
                        p.get("name", "—"),
                        p.get("version", "—"),
                        p.get("author", "—"),
                        caps or "—",
                    )

                console.print(table)
            elif resp.status_code == 404:
                console.print("[dim]Plugins API not found.[/dim]")
            else:
                console.print(f"[red]Error {resp.status_code}[/red]")

    except httpx.ConnectError:
        console.print("[red]❌ Cannot connect to Kimiko.[/red]")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  AGENT (run a task)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
@app.command()
def agent(
    goal: str = typer.Argument(..., help="The goal for the agent to accomplish."),
    max_steps: int = typer.Option(5, help="Maximum reasoning steps."),
):
    """Run an agent task with reasoning and tools."""
    console.print()
    console.print(f"[dim]🤖 Agent Goal: {goal}[/dim]")
    console.print()

    payload = {"goal": goal, "max_steps": max_steps}

    try:
        with httpx.Client(timeout=180.0, headers=_get_headers()) as client:
            resp = client.post(f"{API_URL}/agent/run", json=payload)

            if resp.status_code == 200:
                data = resp.json()
                answer = data.get("answer", "No answer.")
                steps = data.get("steps", [])

                if steps:
                    console.print(Panel(
                        "\n".join([f"[dim]Step {i+1}:[/dim] {s}" for i, s in enumerate(steps)]),
                        title="Agent Reasoning",
                        border_style="yellow",
                    ))

                console.print(Panel(
                    Markdown(answer),
                    title="🏯 Agent Result",
                    border_style="green",
                    padding=(1, 2),
                ))
            else:
                console.print(f"[red]Error {resp.status_code}: {resp.text}[/red]")

    except httpx.ConnectError:
        console.print("[red]❌ Cannot connect to Kimiko.[/red]")


def main():
    app()


if __name__ == "__main__":
    main()

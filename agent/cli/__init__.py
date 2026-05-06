# agent/cli/__init__.py
import typer, asyncio, json, sys, logging
from rich.console import Console
from rich.table import Table

from agent.cli.ask import ask as ask_command
from agent.cli.fix import fix as fix_command
from agent.cli.memory import app as memory_group

app = typer.Typer(
    name="devops-agent",
    help="CLI для DevOps AI Agent",
    no_args_is_help=True,
    rich_markup_mode="rich"
)

app.command()(ask_command)
app.command()(fix_command)
app.add_typer(memory_group, name="memory")

@app.command("status")
def show_status():
    """Показать статус компонентов агента"""
    import httpx
    
    console = Console()
    table = Table(title="DevOps Agent Status")
    table.add_column("Component", style="cyan")
    table.add_column("Status", style="green")
    table.add_column("Details", style="dim")
    
    async def check_service(url: str, name: str):
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                r = await client.get(url)
                return name, "✓ OK" if r.status_code == 200 else "✗ Error", str(r.status_code)
        except Exception as e:
            return name, "✗ Down", str(e)
    
    async def run_checks():
        checks = [
            ("http://localhost:8000/health", "vLLM"),
            ("http://localhost:8080/health", "Agent API"),
            ("http://localhost:6333/readyz", "Qdrant"),
        ]
        results = await asyncio.gather(*[check_service(url, name) for url, name in checks])
        for name, status, details in results:
            table.add_row(name, status, details)
        console.print(table)
    
    asyncio.run(run_checks())

@app.command("audit")
def show_audit(audit_id: str = typer.Argument(..., help="ID аудита")):
    """Показать детали выполнения по audit_id"""
    import httpx
    
    async def fetch():
        async with httpx.AsyncClient() as client:
            r = await client.get(f"http://localhost:8080/api/v1/audit/{audit_id}")
            if r.status_code == 404:
                print(f"❌ Audit record '{audit_id}' not found")
                sys.exit(1)
            r.raise_for_status()
            data = r.json()
            print(json.dumps(data, indent=2, ensure_ascii=False))
    
    asyncio.run(fetch())

if __name__ == "__main__":
    app()

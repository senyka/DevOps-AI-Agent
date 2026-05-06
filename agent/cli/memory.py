# agent/cli/memory.py
import typer, asyncio, json, sys, httpx
from typing import Optional, Literal
from rich.console import Console
from rich.table import Table
from datetime import datetime

app = typer.Typer()

@app.command("search")
def search(
    query: str = typer.Argument(..., help="Поисковый запрос"),
    project: Optional[str] = typer.Option(None, "--project", "-p"),
    limit: int = typer.Option(10, "--limit", "-l", min=1, max=50),
    format: Literal["table", "json"] = typer.Option("table", "--format")
):
    """Поиск в памяти ошибок"""
    
    async def run():
        async with httpx.AsyncClient() as client:
            params = {"query": query, "limit": limit}
            if project:
                params["project"] = project
            
            resp = await client.get("http://localhost:8080/api/v1/memory/errors", params=params)
            resp.raise_for_status()
            results = resp.json()
            
            if format == "json":
                print(json.dumps(results, indent=2, ensure_ascii=False))
            else:
                console = Console()
                table = Table(title=f"Результаты поиска: '{query}'")
                table.add_column("ID", style="dim")
                table.add_column("Signature")
                table.add_column("Project")
                table.add_column("Fix Steps", max_width=50)
                table.add_column("Score", justify="right")
                
                for r in results:
                    table.add_row(
                        r["id"][:8],
                        r["signature"][:30] + "..." if len(r["signature"]) > 30 else r["signature"],
                        r.get("project", "N/A"),
                        "; ".join(r.get("fix_steps", [])[:2]),
                        f"{r['score']:.2f}"
                    )
                console.print(table)
    
    asyncio.run(run())

@app.command("consolidate")
def consolidate(
    since: str = typer.Option("24h", "--since", help="Период: 1h, 24h, 7d"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Предпросмотр без применения"),
    force: bool = typer.Option(False, "--force", help="Пропустить проверку")
):
    """Запустить консолидацию памяти"""
    
    async def run():
        async with httpx.AsyncClient(timeout=120) as client:
            payload = {"since": since, "dry_run": dry_run, "force": force}
            
            console = Console()
            with console.status("[bold green]Консолидация...", spinner="dots"):
                resp = await client.post(
                    "http://localhost:8080/api/v1/memory/consolidate",
                    json=payload
                )
            
            if resp.status_code == 200:
                result = resp.json()
                console.print(f"[green]✓ Консолидация завершена[/]")
                console.print(f"  • Обработано кейсов: {result.get('processed', 0)}")
                console.print(f"  • Обновлено в KG: {result.get('kg_updates', 0)}")
                console.print(f"  • LoRA dataset: +{result.get('new_samples', 0)} записей")
            else:
                console.print(f"[red]✗ Error {resp.status_code}[/]: {resp.text}")
    
    asyncio.run(run())

@app.command("export")
def export(
    output: str = typer.Option("export.json", "--output", "-o"),
    format: Literal["json", "markdown", "csv"] = typer.Option("json", "--format"),
    project: Optional[str] = typer.Option(None, "--project", "-p")
):
    """Экспорт памяти в файл"""
    
    async def run():
        async with httpx.AsyncClient() as client:
            params = {"format": format}
            if project:
                params["project"] = project
            
            resp = await client.get("http://localhost:8080/api/v1/memory/export", params=params)
            resp.raise_for_status()
            
            with open(output, "w", encoding="utf-8") as f:
                if format == "json":
                    json.dump(resp.json(), f, indent=2, ensure_ascii=False)
                else:
                    f.write(resp.text)
            
            typer.echo(f"✓ Экспортировано в {output} ({len(resp.content)} bytes)")
    
    asyncio.run(run())


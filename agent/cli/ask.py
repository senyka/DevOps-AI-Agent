# agent/cli/ask.py
import typer, asyncio, json, sys, httpx
from pathlib import Path
from typing import Optional
from rich.console import Console
from rich.markdown import Markdown

app = typer.Typer()

@app.command()
def ask(
    task: str = typer.Option(..., "--task", "-t", help="Описание задачи"),
    project: Optional[str] = typer.Option(None, "--project", "-p", help="Проект: group/project"),
    error: Optional[str] = typer.Option(None, "--error", "-e", help="Текст ошибки"),
    context_file: Optional[Path] = typer.Option(None, "--context-file", "-f", help="Файл с контекстом"),
    mode: str = typer.Option("advisory", "--mode", "-m", help="Режим: advisory или autonomous"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Подробный вывод")
):
    """Задать вопрос агенту или описать ошибку"""
    
    # Чтение контекста из файла
    context = None
    if context_file and context_file.exists():
        context = context_file.read_text(encoding="utf-8")
        if verbose:
            typer.echo(f"📄 Loaded context from {context_file} ({len(context)} chars)")
    
    # Формирование запроса
    payload = {
        "task": task,
        "project_path": project,
        "error_context": error or context,
        "mode": mode
    }
    
    async def send():
        async with httpx.AsyncClient(timeout=180) as client:
            console = Console()
            with console.status("[bold green]Думаю...", spinner="dots"):
                resp = await client.post(
                    "http://localhost:8080/api/v1/query",
                    json=payload,
                    headers={"Content-Type": "application/json"}
                )
            
            if resp.status_code != 200:
                typer.echo(f"❌ Error {resp.status_code}: {resp.text}", err=True)
                sys.exit(1)
            
            result = resp.json()
            
            # Вывод результата
            console.print(f"\n[bold blue]💡 Ответ (уверенность: {result['confidence']:.0%}):[/]")
            if isinstance(result["answer"], str):
                console.print(Markdown(result["answer"]))
            else:
                console.print(json.dumps(result["answer"], indent=2, ensure_ascii=False))
            
            if result.get("next_steps"):
                console.print("\n[bold]📋 Следующие шаги:[/]")
                for i, step in enumerate(result["next_steps"], 1):
                    console.print(f"  {i}. {step}")
            
            if result["requires_approval"]:
                console.print("\n[bold yellow]⚠  Требуется подтверждение для выполнения[/]")
                console.print("Используйте: devops-agent fix --audit-id " + result["audit_id"])
            
            if verbose:
                console.print(f"\n[dim]Audit ID: {result['audit_id']}[/]")
    
    asyncio.run(send())


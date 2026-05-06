# agent/cli/fix.py
import typer, asyncio, json, sys, httpx, time
from typing import Optional
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

app = typer.Typer()

@app.command()
def fix(
    project: str = typer.Option(..., "--project", "-p", help="Проект: group/project"),
    job_id: Optional[str] = typer.Option(None, "--job-id", "-j", help="ID job в GitLab CI"),
    audit_id: Optional[str] = typer.Option(None, "--audit-id", help="Продолжить по audit_id"),
    auto_approve: str = typer.Option("logs,inspect,df", "--auto-approve", help="Команды без подтверждения"),
    require_approve: str = typer.Option("restart,rm,systemctl", "--require-approve", help="Команды с подтверждением"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Только показать план, не выполнять")
):
    """Запустить автономное исправление ошибки"""
    
    console = Console()
    
    # Если указан audit_id — продолжаем существующую сессию
    if audit_id:
        console.print(f"🔄 Продолжаю сессию {audit_id}")
        # Логика continuation...
        return
    
    # Формирование начального запроса
    payload = {
        "task": f"Автономное исправление в проекте {project}",
        "project_path": project,
        "error_context": f"GitLab job {job_id}" if job_id else "Пользовательский запрос на исправление",
        "mode": "autonomous"
    }
    
    async def run_fix():
        async with httpx.AsyncClient(timeout=300) as client:
            # 1. Получаем план
            with console.status("[bold green]Анализирую...", spinner="dots"):
                resp = await client.post("http://localhost:8080/api/v1/query", json=payload)
            
            if resp.status_code != 200:
                typer.echo(f"❌ Error: {resp.text}", err=True)
                sys.exit(1)
            
            result = resp.json()
            plan = result.get("next_steps", [])
            
            if not plan:
                console.print("[yellow]⚠ План не сгенерирован — требую уточнения[/]")
                return
            
            # 2. Показываем план
            console.print("\n[bold]📋 Предложенный план:[/]")
            for i, step in enumerate(plan, 1):
                approval = "🔓" if step.lower().split()[0] in auto_approve.split(",") else "🔐"
                console.print(f"  {approval} {i}. {step}")
            
            if dry_run:
                console.print("\n[dry-run mode] Выполнение пропущено")
                return
            
            # 3. Интерактивное подтверждение опасных шагов
            dangerous = [s for s in plan if any(p in s.lower() for p in require_approve.split(","))]
            if dangerous and not typer.confirm(f"⚠ Выполнить {len(dangerous)} потенциально опасных команд?"):
                console.print("[yellow]Отменено пользователем[/]")
                return
            
            # 4. Выполнение (упрощённо — в реальности через WebSocket/streaming)
            with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}")) as progress:
                task = progress.add_task("[green]Выполняю...", total=len(plan))
                
                for i, step in enumerate(plan):
                    progress.update(task, description=f"Шаг {i+1}/{len(plan)}: {step[:40]}...")
                    # В реальности: отправка шага на выполнение через API
                    await asyncio.sleep(1)  # Имитация
                    progress.advance(task)
            
            console.print("\n[bold green]✓ Выполнение завершено[/]")
            console.print(f"📊 Audit: {result['audit_id']}")
    
    asyncio.run(run_fix())


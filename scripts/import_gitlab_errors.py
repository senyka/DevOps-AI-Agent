import os, sys, json, asyncio, logging
import httpx, asyncpg
from datetime import datetime, timedelta
from gitlab import Gitlab

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

GITLAB_URL = os.getenv("GITLAB_URL", "https://gitlab.dash-panel.tech")
GITLAB_TOKEN = os.getenv("GITLAB_TOKEN")
DB_URL = os.getenv("DATABASE_URL")

async def main():
    if not GITLAB_TOKEN:
        logger.error("Set GITLAB_TOKEN environment variable")
        sys.exit(1)
    
    # Подключение к БД
    pool = await asyncpg.create_pool(DB_URL)
    
    # GitLab client
    gl = Gitlab(GITLAB_URL, private_token=GITLAB_TOKEN)
    
    # Получение проектов (или взять из конфига)
    projects = os.getenv("GITLAB_PROJECTS", "dash-panel/backend,dash-panel/frontend").split(",")
    
    imported = 0
    for proj_name in projects:
        logger.info(f"Processing project: {proj_name}")
        project = gl.projects.get(proj_name)
        
        # Пайплайны за последние 7 дней
        cutoff = datetime.utcnow() - timedelta(days=7)
        pipelines = project.pipelines.list(get_all=True, updated_after=cutoff.isoformat())
        
        for pipeline in pipelines:
            if pipeline.status != "failed":
                continue
            
            # Получение упавших jobs
            for job in pipeline.jobs.list():
                if job.status != "failed":
                    continue
                
                # Извлечение логов
                try:
                    logs = job.trace().decode("utf-8", errors="ignore")[:5000]
                except:
                    continue
                
                # Формирование кейса
                case = {
                    "signature": f"{job.name}:{pipeline.sha[:8]}",
                    "stacktrace": logs,
                    "context": {
                        "project": proj_name,
                        "pipeline_id": pipeline.id,
                        "job_id": job.id,
                        "stage": job.stage,
                        "ref": pipeline.ref
                    },
                    "project": proj_name,
                    "status": "pending"  # Требует анализа
                }
                
                # Сохранение в БД
                async with pool.acquire() as conn:
                    await conn.execute("""
                        INSERT INTO error_cases (signature, stacktrace, context, project, status)
                        VALUES ($1, $2, $3, $4, $5)
                        ON CONFLICT (signature) DO UPDATE 
                        SET updated_at = NOW(), stacktrace = EXCLUDED.stacktrace
                    """, 
                        case["signature"], case["stacktrace"], 
                        json.dumps(case["context"]), case["project"], case["status"]
                    )
                imported += 1
    
    await pool.close()
    logger.info(f"✓ Imported {imported} error cases")

if __name__ == "__main__":
    asyncio.run(main())

# worker/monitor.py
import os, json, logging, httpx
from datetime import datetime
from celery import Celery
from celery.schedules import crontab

logger = logging.getLogger(__name__)

app = Celery("monitor", broker=os.getenv("REDIS_URL"))

# Расписание задач
app.conf.beat_schedule = {
    "validate-adapter-hourly": {
        "task": "worker.tasks.validate_active_adapter",
        "schedule": crontab(minute=0),  # Каждый час
    },
    "cleanup-old-lora-daily": {
        "task": "cleanup_old_lora_adapters",
        "schedule": crontab(hour=3, minute=0),  # 3 AM ежедневно
    }
}

@app.task
def cleanup_old_lora_adapters(keep_last: int = 5):
    """Удаление старых версий LoRA для экономии места"""
    import glob, shutil
    adapters = sorted(glob.glob("/lora/devops_v*"), key=lambda p: os.path.getmtime(p), reverse=True)
    
    removed = 0
    for adapter in adapters[keep_last:]:
        try:
            shutil.rmtree(adapter)
            logger.info(f"Removed old adapter: {adapter}")
            removed += 1
        except Exception as e:
            logger.error(f"Failed to remove {adapter}: {e}")
    
    return {"removed": removed, "kept": len(adapters[:keep_last])}


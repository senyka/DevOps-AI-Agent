# worker/tasks.py
import os, json, logging, asyncio
from celery import Celery
from datetime import datetime, timedelta

from agent.memory import init_stores, search_error_cases, update_knowledge_graph
from agent.llm import call_vllm
from worker.train import train_lora_adapter
from worker.validate import run_ragas_validation

logger = logging.getLogger(__name__)

app = Celery("devops_worker", broker=os.getenv("REDIS_URL"))
app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=7200,  # 2 часа макс. на задачу
    worker_prefetch_multiplier=1
)

@app.task(bind=True, max_retries=3)
def consolidate_memory(self, audit_id: str = None, since: str = "24h"):
    """Консолидация памяти: рефлексия → извлечение паттернов → обновление хранилищ"""
    
    try:
        # 1. Сбор новых успешных кейсов
        cutoff = datetime.utcnow() - parse_duration(since)
        new_cases = fetch_new_cases(cutoff, status="success")
        
        if not new_cases:
            logger.info("No new cases to consolidate")
            return {"processed": 0}
        
        logger.info(f"Processing {len(new_cases)} new cases")
        
        # 2. Рефлексия и экстракция (через LLM)
        patterns = []
        for case in new_cases:
            pattern = extract_pattern_via_llm(case)
            if pattern:
                patterns.append(pattern)
                # Обновляем граф знаний
                asyncio.run(update_knowledge_graph(
                    error_sig=case["signature"],
                    fix_steps=pattern["steps"],
                    root_cause=pattern.get("root_cause")
                ))
        
        # 3. Формирование датасета для LoRA
        if len(patterns) >= 20:  # Порог для обучения
            dataset_path = generate_lora_dataset(patterns)
            # Запускаем обучение (асинхронно)
            train_lora_adapter.delay(dataset_path, version=f"v{next_version()}")
        
        # 4. Обновляем статус кейсов
        mark_consolidated([c["id"] for c in new_cases])
        
        return {
            "processed": len(new_cases),
            "patterns_extracted": len(patterns),
            "kg_updates": len(patterns),
            "new_samples": len(patterns)
        }
        
    except Exception as e:
        logger.exception("Consolidation failed")
        raise self.retry(exc=e, countdown=300)

@app.task(bind=True, max_retries=2)
def train_lora_adapter(self, dataset_path: str, version: str):
    """Fine-tuning LoRA адаптера на успешных кейсах"""
    
    try:
        logger.info(f"Starting LoRA training: {version}")
        
        # 1. Валидация датасета
        if not validate_dataset(dataset_path):
            raise ValueError("Dataset validation failed")
        
        # 2. Запуск обучения (unsloth)
        output_dir = f"/lora/devops_{version}"
        metrics = run_unsloth_training(
            dataset_path=dataset_path,
            output_dir=output_dir,
            config_path="/app/configs/devops_lora.yaml"
        )
        
        # 3. Валидация качества
        val_metrics = run_ragas_validation(output_dir)
        if val_metrics["answer_relevance"] < 0.85:
            logger.warning(f"Validation failed: {val_metrics}")
            return {"status": "rejected", "metrics": val_metrics}
        
        # 4. Регистрация в vLLM
        register_lora_in_vllm(f"devops_{version}", output_dir)
        
        logger.info(f"✓ LoRA {version} deployed")
        return {"status": "deployed", "adapter": f"devops_{version}", "metrics": {**metrics, **val_metrics}}
        
    except Exception as e:
        logger.exception(f"Training failed: {e}")
        # Откат: удаляем частичный адаптер
        cleanup_lora_dir(f"/lora/devops_{version}")
        raise self.retry(exc=e, countdown=600)

@app.task
def validate_active_adapter():
    """Ежечасная проверка качества активного LoRA адаптера"""
    adapter = get_active_lora_name()
    if not adapter:
        return
    
    metrics = run_ragas_validation(adapter, test_file="/data/holdout_devops.jsonl")
    
    if metrics["answer_relevance"] < 0.80 or metrics["faithfulness"] < 0.75:
        logger.warning(f"Adapter {adapter} degraded — triggering rollback")
        rollback_lora(adapter)
        send_alert(f"LoRA rollback: {adapter} due to metric regression")
    
    return {"adapter": adapter, "metrics": metrics}

# === Helpers ===

def parse_duration(s: str) -> timedelta:
    """Парсинг строки длительности: '24h' → timedelta(hours=24)"""
    import re
    match = re.match(r"^(\d+)([hdw])$", s)
    if not match:
        raise ValueError(f"Invalid duration: {s}")
    value, unit = int(match[1]), match[2]
    return {"h": timedelta(hours=value), "d": timedelta(days=value), "w": timedelta(weeks=value)}[unit]

def fetch_new_cases(cutoff: datetime, status: str = "success") -> list[dict]:
    """Получение новых кейсов из БД"""
    # Реализация через agent.memory.search_error_cases с фильтрами
    pass

def extract_pattern_via_llm(case: dict) -> Optional[dict]:
    """Извлечение паттерна через LLM (root cause + универсальные шаги)"""
    prompt = f"""
    Проанализируй успешное исправление ошибки и выдели универсальный паттерн.
    
    Ошибка: {case["signature"]}
    Контекст: {case["stacktrace"][:500]}
    Шаги фикса: {json.dumps(case["fix_steps"])}
    
    Верни JSON:
    {{
      "root_cause": "краткое описание причины",
      "steps": ["универсальный шаг 1", "шаг 2", ...],
      "validation": "команда для проверки",
      "applicable_projects": ["pattern for project names"]
    }}
    """
    
    response = asyncio.run(call_vllm(prompt, temperature=0.0, response_format={"type": "json_object"}))
    return json.loads(response) if response else None

def generate_lora_dataset(patterns: list[dict]) -> str:
    """Генерация JSONL датасета в формате Alpaca"""
    import json
    output_path = f"/data/datasets/devops_fixes_{datetime.now():%Y%m%d_%H%M}.jsonl"
    
    with open(output_path, "w", encoding="utf-8") as f:
        for p in patterns:
            sample = {
                "instruction": f"Fix error: {p['root_cause']}",
                "input": f"Context: Docker/GitLab environment\nError signature: {p['signature']}",
                "output": "\n".join([f"{i+1}. {s}" for i, s in enumerate(p["steps"])]) + f"\n\nValidate: {p['validation']}"
            }
            f.write(json.dumps(sample, ensure_ascii=False) + "\n")
    
    return output_path

def next_version() -> int:
    """Определение следующего номера версии LoRA"""
    import glob
    existing = [int(p.split("_v")[1]) for p in glob.glob("/lora/devops_v*") if p.split("_v")[1].isdigit()]
    return max(existing, default=0) + 1

def register_lora_in_vllm(name: str, path: str):
    """Регистрация адаптера в vLLM через API"""
    import httpx
    with httpx.Client(timeout=30) as client:
        resp = client.post(
            "http://vllm:8000/v1/lora",
            json={"lora_name": name, "lora_path": path},
            headers={"Content-Type": "application/json"}
        )
        resp.raise_for_status()

def rollback_lora(adapter_name: str):
    """Откат к предыдущему адаптеру"""
    import subprocess
    subprocess.run(["/app/scripts/lora_manager.sh", adapter_name, "rollback"], check=True)

def send_alert(message: str):
    """Отправка алерта (в будущем: Slack/Email/Telegram)"""
    logger.critical(f"🚨 ALERT: {message}")
    # В продакшене: отправка в мониторинговую систему

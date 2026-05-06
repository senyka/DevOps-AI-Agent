# 🤖 DevOps AI Agent — Персональный исследовательский ассистент

> **Автономный мультиагентный помощник для разработки, администрирования и развёртывания**  
> 🧠 Глубокие рассуждения • 🗃️ Долгосрочная память • 🔁 Непрерывное обучение • 🔐 Полностью локально

```
🎯 Предназначение: Анализ ошибок, генерация кода, управление Docker/GitLab, 
   автономное исправление инцидентов с сохранением опыта в памяти.

🖥️ Управление: Терминал (CLI) + Web UI (опционально) — без Telegram/Slack.

🔒 Приватность: Все данные обрабатываются локально, нет внешних API-вызовов.
```

---

## 📋 Оглавление

1. [Архитектура](#-архитектура)
2. [Структура проекта](#-структура-проекта)
3. [Требования](#-требования)
4. [Быстрый старт](#-быстрый-старт)
5. [Конфигурация](#-конфигурация)
6. [Использование](#-использование)
7. [Логика работы](#-логика-работы)
8. [Память и обучение](#-память-и-непрерывное-обучение)
9. [Безопасность](#-безопасность)
10. [Мониторинг](#-мониторинг)
11. [Troubleshooting](#-troubleshooting)
12. [Предложения по улучшению](#-предложения-по-улучшению)
13. [Лицензия](#-лицензия)

---

## 🏗️ Архитектура

```
┌─────────────────────────────────────────────────────┐
│                   USER INTERFACE                    │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  │
│  │    CLI      │  │  FastAPI    │  │  Open WebUI │  │
│  │ (terminal)  │  │  /docs      │  │ (optional)  │  │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘  │
└─────────┼────────────────┼────────────────┼─────────┘
          │                │                │
          ▼                ▼                ▼
┌──────────────────────────────────────────────────────┐
│                  AGENT CORE                          │
│  ┌──────────────────────────────────────────┐        │
│  │           LangGraph State Machine        │        │
│  │  ┌─────────┐ ┌─────────┐ ┌─────────┐     │        │
│  │  │Research │→│ Plan    │→│ Execute │     │        │
│  │  └─────────┘ └─────────┘ └────┬────┘     │        │
│  │                               │          │        │
│  │                    ┌──────────▼────────┐ │        │
│  │                    │   Reflect & Store │ │        │
│  │                    └───────────────────┘ │        │
│  └──────────────────────────────────────────┘        │
└────────────────────┬─────────────────────────────────┘
                     │
     ┌───────────────┼───────────────┐
     ▼               ▼               ▼
┌─────────┐  ┌─────────┐  ┌─────────────────┐
│  Tools  │  │ Memory  │  │  Learning Loop  │
│         │  │         │  │                 │
│ • Docker│  │ • Qdrant│  │ • Unsloth/TRL   │
│ • GitLab│  │ • Neo4j │  │ • RAGAS eval    │
│ • Shell │  │ • PG+pgv│  │ • vLLM hot-swap │
│ • Code  │  │ • Check │  │ • Celery tasks  │
└─────────┘  └─────────┘  └─────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────────────────┐
│                 INFERENCE LAYER                     │
│  ┌─────────────────────────────────────────┐        │
│  │  vLLM + Qwen2.5-14B-Instruct-AWQ + LoRA │        │
│  │  • PagedAttention • Prefix caching      │        │
│  │  • Dynamic LoRA loading (hot-swap)      │        │
│  └─────────────────────────────────────────┘        │
└─────────────────────────────────────────────────────┘
```

### Ключевые компоненты

| Компонент | Назначение | Технология |
|-----------|-----------|------------|
| **LLM Engine** | Генерация ответов, рассуждения, tool-calling | `vLLM` + `Qwen2.5-14B-Instruct-AWQ` |
| **Agent Framework** | Управление состоянием, циклы, чекпоинты | `LangGraph` + `AsyncPostgresSaver` |
| **Vector Memory** | Семантический поиск ошибок и решений | `Qdrant` + `bge-m3` эмбеддинги |
| **Knowledge Graph** | Связи `Error → RootCause → Fix` | `Neo4j` + Cypher queries |
| **State Storage** | Чекпоинты, аудит, метаданные | `PostgreSQL 16` + `pgvector` |
| **Task Queue** | Фоновая консолидация, обучение | `Celery` + `Redis` |
| **Continuous Learning** | LoRA fine-tuning на успешных кейсах | `Unsloth` + `TRL` + `RAGAS` |

---

## 📁 Структура проекта

```
devops-agent/
├── 📄 docker-compose.yml          # Полный стек: vLLM, Qdrant, Neo4j, PG, Redis
├── 📄 .env.example                # Шаблон переменных окружения
├── 📄 README.md                   # Этот файл
│
├── 📁 agent/                      # Основной код агента
│   ├── 📄 Dockerfile
│   ├── 📄 main.py                 # FastAPI entrypoint + CLI handler
│   ├── 📄 graph.py                # LangGraph state machine (research→plan→execute→reflect)
│   ├── 📄 tools.py                # Инструменты: docker_exec, gitlab_api, shell_safe
│   ├── 📄 llm.py                  # vLLM client с JSON-mode и retry-логикой
│   ├── 📄 memory.py               # Абстракции для Qdrant/Neo4j/PostgreSQL
│   ├── 📄 schemas.py              # Pydantic-модели для валидации вход/выход
│   └── 📁 cli/                    # CLI-команды (argparse/typer)
│       ├── 📄 __init__.py
│       ├── 📄 ask.py              # devops-agent ask --project X --error Y
│       ├── 📄 fix.py              # devops-agent fix --auto-approve ...
│       └── 📄 memory.py           # devops-agent memory search/consolidate
│
├── 📁 worker/                     # Фоновые задачи (Celery)
│   ├── 📄 Dockerfile
│   ├── 📄 tasks.py                # consolidate_memory, train_lora_adapter
│   ├── 📄 monitor.py              # Валидация адаптеров, auto-rollback
│   └── 📁 configs/
│       └── 📄 devops_lora.yaml    # Axolotl/Unsloth конфиг обучения
│
├── 📁 init/                       # Инициализация БД
│   ├── 📄 01_schema.sql           # Таблицы: error_cases, audit_log, lora_versions
│   └── 📄 02_indexes.sql          # GIN-индексы, триггеры updated_at
│
├── 📁 config/                     # Конфигурация сервисов
│   ├── 📄 qdrant.yaml             # HNSW + sparse index settings
│   └── 📄 neo4j.conf              # Page cache, heap tuning
│
├── 📁 scripts/                    # Утилиты развёртывания
│   ├── 📄 lora_manager.sh         # load/unload/rollback LoRA в vLLM
│   ├── 📄 import_gitlab_errors.py # Импорт истории падений из GitLab CI
│   └── 📄 backup.sh               # Snapshot PG + Qdrant + Neo4j
│
├── 📁 data/                       # Данные (игнорируются в .git)
│   ├── 📁 models/                 # Кэш HuggingFace (монтируется из хоста)
│   ├── 📁 holdout/                # Тестовый набор для валидации
│   └── 📁 datasets/               # Сгенерированные датасеты для LoRA
│
├── 📁 lora_adapters/              # Скомпилированные LoRA-адаптеры
│   ├── 📄 .gitkeep
│   └── 📄 devops_v1/              # Пример: adapter_config.json + adapter_model.safetensors
│
├── 📁 logs/                       # Логи (ротация через logrotate)
│   ├── 📄 agent.log
│   ├── 📄 vllm.log
│   └── 📄 audit.jsonl             # Структурированный аудит-лог
│
└── 📁 monitoring/                 # Prometheus + Grafana (опционально)
    ├── 📄 prometheus.yml
    └── 📁 dashboards/
        └── 📄 devops-agent.json   # Готовый дашборд: VRAM, confidence, error_rate
```

---

## ⚙️ Требования

### Аппаратные (рекомендуемые)
| Компонент | Минимум | Рекомендуется |
|-----------|---------|---------------|
| **GPU** | NVIDIA RTX 3090 (24GB) | **RTX 4090 (24GB)** |
| **RAM** | 32 GB | **64 GB+** |
| **Storage** | 500 GB NVMe | **2 TB+ NVMe** |
| **CPU** | 6 ядер | 12+ ядер (для ingestion/CPU-эмбеддингов) |

### Программные
```bash
# Обязательные
- Docker 24.0+
- Docker Compose v2.20+
- NVIDIA Container Toolkit (для GPU-доступа в контейнерах)
- Git 2.40+

# Опционально (для разработки)
- Python 3.11+
- huggingface-cli (для загрузки моделей)
- make (для удобства скриптов)
```

### Проверка окружения
```bash
# Проверка Docker + GPU
docker run --rm --gpus all nvidia/cuda:12.4.1-base-ubuntu22.04 nvidia-smi

# Проверка памяти и диска
free -h && df -h /data

# Проверка прав доступа к Docker (если не используете sudo)
groups $USER | grep docker || echo "⚠ Добавьте пользователя в группу docker"
```

---

## 🚀 Быстрый старт

### Шаг 1: Клонирование и настройка
```bash
# Клонировать репозиторий (замените на ваш URL в gitlab.dash-panel.tech)
git clone https://gitlab.dash-panel.tech/tr0jan/devops-agent.git
cd devops-agent

# Создать .env из шаблона
cp .env.example .env

# Отредактировать .env (см. раздел Конфигурация ниже)
nano .env  # или ваш любимый редактор
```

### Шаг 2: Загрузка модели (однократно)
```bash
# Создать директорию для моделей (если не существует)
mkdir -p /data/models

# Скачать модель через huggingface-cli
huggingface-cli download Qwen/Qwen2.5-14B-Instruct-AWQ \
  --local-dir /data/models/Qwen2.5-14B-Instruct-AWQ \
  --local-dir-use-symlinks false \
  --resume-download

# Альтернатива: использовать skypilot для распределённой загрузки
# pip install skypilot
# sky launch --cloud local --gpus A100:1 --setup "huggingface-cli download ..."
```

### Шаг 3: Запуск стека
```bash
# Запустить все сервисы в фоне
docker-compose up -d

# Проверить статус
docker-compose ps

# Ожидать готовности (30-60 сек)
watch -n 5 'docker-compose ps | grep -E "(healthy|Exit)"'
```

### Шаг 4: Проверка подключения
```bash
# vLLM API
curl -s http://localhost:8000/health | jq

# Agent API
curl -s http://localhost:8080/health | jq

# Qdrant
curl -s http://localhost:6333/readyz

# Neo4j (требует авторизации)
curl -u neo4j:$NEO4J_PASSWORD http://localhost:7474/db/manage/server/status
```

### Шаг 5: Первый запрос через CLI
```bash
# Установить CLI-утилиту (опционально, можно использовать curl)
pip install -e ./agent[cli]

# Простой запрос
devops-agent ask \
  --task "Почему падает docker-compose up?" \
  --context-file ./error.log

# Запрос с привязкой к проекту в GitLab
devops-agent ask \
  --project "dash-panel/backend" \
  --error "gitlab-runner: exit code 137 (OOMKilled)" \
  --context "$(cat ./build.log)"
```

---

## 🔧 Конфигурация

### Файл `.env` (ключевые переменные)
```bash
# === Секреты (обязательно изменить!) ===
NEO4J_PASSWORD=YourSecureNeo4jPass_2026!
POSTGRES_PASSWORD=YourSecurePGPass_2026!
GITLAB_TOKEN=glpat-xxxxxxxxxxxxxxxxxxxx  # Personal Access Token: api, read_repository

# === GitLab ===
GITLAB_URL=https://gitlab.dash-panel.tech
GITLAB_DEFAULT_PROJECT=dash-panel/backend  # Опционально: проект по умолчанию

# === Агент ===
AGENT_MODE=autonomous          # autonomous | advisory (только рекомендации)
MAX_RETRY=3                    # Макс. попыток исправления одной ошибки
CONFIDENCE_THRESHOLD=0.7       # Порог уверенности для авто-исполнения
SANDBOX_TIMEOUT=120            # Таймаут выполнения команд в секундах

# === Модель ===
VLLM_MODEL=Qwen/Qwen2.5-14B-Instruct-AWQ
VLLM_MAX_LEN=8192              # Контекст: 8192 токенов
VLLM_GPU_UTIL=0.85             % Загрузка GPU (оставить запас для LoRA)

# === Пути (монтируются в контейнеры) ===
MODELS_DIR=/data/models
LORA_DIR=./lora_adapters
LOGS_DIR=./logs
```

> 🔐 **Важно**: Никогда не коммитьте `.env` в репозиторий. Добавьте его в `.gitignore`.

---

## 💻 Использование

### CLI-команды
```bash
# 📝 Задать вопрос / описать ошибку
devops-agent ask \
  --task "Описание проблемы" \
  [--project "group/project"] \
  [--error "текст ошибки"] \
  [--context-file ./file.log] \
  [--verbose]

# 🔧 Запустить автономное исправление
devops-agent fix \
  --project "dash-panel/backend" \
  --job-id 12345 \
  --auto-approve="logs,inspect,df" \          # Команды без подтверждения
  --require-approve="restart,rm,systemctl"    # Команды с подтверждением

# 🗃️ Работа с памятью
devops-agent memory search "docker" --limit 10 --project "dash-panel/*"
devops-agent memory consolidate --since "24h" --dry-run   # Предпросмотр изменений
devops-agent memory export --format json --output ./backup.json

# 📊 Статус и аудит
devops-agent status          # Здоровье компонентов, VRAM, активный LoRA
devops-agent audit --id abc123  # Детали выполнения по audit_id
```

### API-эндпоинты (FastAPI)
```
GET  /health                          # Статус агента и зависимостей
POST /api/v1/query                    # Основной запрос (JSON)
{
  "task": "string",
  "project_path": "string (optional)",
  "error_context": "string (optional)",
  "mode": "advisory|autonomous"
}

GET  /api/v1/memory/errors?query=... # Поиск в памяти ошибок
POST /api/v1/memory/consolidate      # Запуск консолидации (требует auth)
GET  /api/v1/audit/{audit_id}        # Детали выполнения + логи
WS   /ws/agent                       # WebSocket для стриминга "мыслей" агента
```

### Пример запроса через curl
```bash
curl -X POST http://localhost:8080/api/v1/query \
  -H "Content-Type: application/json" \
  -d '{
    "task": "Исправь OOMKilled в gitlab-runner",
    "project_path": "dash-panel/backend",
    "error_context": "ERROR: Job failed: exit code 137\nMemory limit: 512M",
    "mode": "autonomous"
  }'
```

---

## 🧠 Логика работы (кратко)

### Цикл обработки запроса
```
1. RESEARCH
   ├─ Извлечение сигнатуры ошибки (хеш + ключевые токены)
   ├─ Hybrid search в Qdrant: dense (bge-m3) + sparse (BM25) + metadata filter
   ├─ Graph query в Neo4j: найти связанные ошибки и проверенные фиксы
   └─ Ранжирование результатов по релевантности + успешности

2. PLAN
   ├─ Генерация гипотезы через LLM (temperature=0.1 для детерминированности)
   ├─ Формирование пошагового плана с командами, валидацией и оценкой риска
   ├─ Проверка плана через Pydantic-схемы (валидация команд, таймаутов)
   └─ Оценка уверенности (0.0–1.0) на основе похожих кейсов

3. EXECUTE
   ├─ Пошаговое выполнение в sandbox (Docker с ограничениями)
   ├─ Валидация после каждого шага (exit code, логи, health-check)
   ├─ Early stop при критической ошибке или низком confidence
   └─ Логирование каждого действия в audit-лог

4. REFLECT
   ├─ Анализ результата: успех/частичный успех/провал
   ├─ Обновление confidence (reinforcement learning: +0.05 / -0.1)
   ├─ Если успех + confidence ≥ 0.7 → сохранение в память
   └─ Решение: завершить / повторить планирование / запросить помощь
```

### Обработка ошибок
- **Низкая уверенность** (< 0.6) → возврат к research с расширенным контекстом
- **Провал выполнения** → анализ причины, предложение альтернативы, запрос подтверждения
- **Неизвестная команда** → отказ в выполнении, рекомендация безопасной альтернативы
- **Потеря связи с зависимостями** → graceful degradation (только advisory mode)

---

## 🗃️ Память и непрерывное обучение

### Уровни памяти
| Тип | Хранилище | Обновление | Пример |
|-----|-----------|------------|--------|
| **Эпизодическая** | PostgreSQL (JSONB) | Мгновенно, при каждом действии | Логи сессии, команды, результаты |
| **Семантическая** | Qdrant (bge-m3 векторы) | Асинхронно, после консолидации | Поиск по смыслу: "OOM при сборке" → похожие кейсы |
| **Структурная** | Neo4j (граф) | Пакетно, после валидации | `(Error:137)-[:FIXED_BY]->(Solution:increase_mem)` |
| **Процедурная** | LangGraph State + YAML | При сохранении шаблона | Чек-лист валидации для `docker-compose up` |

### Цикл консолидации (фоновый воркер)
```python
# Запускается каждые 4 часа или по событию (успешный фикс)
1. Сбор новых кейсов: error_cases WHERE status='success' AND consolidated=false
2. Рефлексия: LLM извлекает паттерны, корневые причины, универсальные шаги
3. Экстракция: spaCy/LlamaIndex → сущности → Cypher-запросы для Neo4j
4. Реиндексация: обновление векторов в Qdrant, понижение веса устаревших записей
5. Формирование датасета: успешные кейсы → JSONL для LoRA-обучения
6. Валидация: тестовые запросы → RAGAS метрики → решение об обучении
```

### Непрерывное обучение (LoRA)
```
1. Триггер: ≥20 новых валидированных кейсов ИЛИ плановое обновление (раз в неделю)
2. Обучение: unsloth + TRL на RTX 4090 (~45 мин, 18GB VRAM peak)
3. Валидация: holdout set + RAGAS (faithfulness, answer_relevance ≥0.85)
4. Деплой: hot-swap в vLLM через /v1/lora API (без перезапуска)
5. Мониторинг: если метрики падают >5% → автоматический rollback к предыдущему адаптеру
```

> 🔄 **Результат**: Агент постепенно адаптируется к вашему стеку, стилю кода и типовым ошибкам, не теряя общих знаний.

---

## 🔐 Безопасность

### ✅ Реализованные меры безопасности (v0.2.0)

В версии 0.2.0 добавлен полноценный модуль безопасности `agent/security/` с многоуровневой защитой:

| Компонент | Назначение | Файл |
|-----------|-----------|------|
| **Docker Validator** | Строгий allowlist Docker-команд | `agent/security/docker_validator.py` |
| **Approval System** | Human-in-the-loop для опасных операций | `agent/security/approval.py` |
| **Cypher Sanitizer** | Валидация Cypher-запросов (только чтение) | `agent/security/cypher_sanitizer.py` |
| **Secrets Manager** | Поддержка Docker Secrets + env fallback | `agent/security/secrets.py` |
| **Secure Logging** | Автоматическая маскировка чувствительных данных | `agent/security/logging.py` |
| **Docker Executor** | Изолированный микросервис для Docker-команд | `docker-executor/` |
| **Guardrails Config** | NeMo Guardrails для LLM | `config/guardrails/` |

### 🛡️ Защита от инъекций команд через LLM

#### А. Жёсткий allowlist в `DockerCommand`
```python
from agent.security import validate_docker_command

# Разрешены только: ps, logs, inspect, version, info
is_valid, error = validate_docker_command("docker ps -a")  # True, ""
is_valid, error = validate_docker_command("docker rm container")  # False, "Команда 'rm' не входит в разрешённый список"
```

#### Б. Интеграция в системный промпт LLM
```python
system_prompt = """
Ты – ассистент DevOps. Твоя задача – составлять ТОЛЬКО безопасные docker-команды из разрешённого списка.
Разрешённые команды: docker ps, docker logs, docker inspect.
Ты НЕ ИМЕЕШЬ ПРАВА предлагать команды, которые удаляют, останавливают, убивают контейнеры или используют exec.
"""
```

#### В. Human-in-the-loop с определением опасностей
```python
from agent.security import check_danger, requires_approval

response = "Let me run docker rm -f container123"
is_danger, description, severity = check_danger(response)
# is_danger=True, description="Удаление файлов/контейнеров", severity="critical"

if requires_approval(response):
    # Запросить подтверждение у пользователя
    pass
```

### 🔐 Управление секретами

#### Отказ от `.env` в пользу Docker Secrets (для production)
```bash
# Создание секретов Docker
echo "my_secure_password" | docker secret create db_password -
echo "glpat-xxxxx" | docker secret create gitlab_token -
```

```python
# Чтение секретов в коде
from agent.security import get_secret, get_required_secret

token = get_secret("GITLAB_TOKEN")  # Читает из _FILE или env
password = get_required_secret("DB_PASSWORD")  # ValueError если не найден
```

### 🐳 Безопасная работа с Docker (без монтирования сокета)

Архитектура с изолированным Docker Executor:
- Агент **не имеет доступа** к `/var/run/docker.sock`
- Все Docker-команды выполняются через отдельный микросервис
- Микросервис принимает только разрешённые команды через HTTP API

```bash
# Вызов через API
curl -X POST http://localhost:5001/exec \
  -H "Content-Type: application/json" \
  -d '{"command": "docker ps -a"}'
```

### 🧠 Защита от Prompt Injection (NeMo Guardrails)

Конфигурация в `config/guardrails/rails.co`:
- Блокировка входных паттернов: `rm`, `kill`, `delete`, `exec`, `drop`
- Блокировка выходных паттернов: `docker rm`, `docker kill`, `docker exec`
- Автоматический отказ с сообщением о политиках безопасности

### 📊 Валидация Cypher-запросов

```python
from agent.security import is_cypher_safe

is_safe, error = is_cypher_safe("MATCH (n) RETURN n")  # True, ""
is_safe, error = is_cypher_safe("DELETE (n)")  # False, "Запрещённая операция"
is_safe, error = is_cypher_safe("MATCH (n) SET n.status = 'active'")  # False, "SET запрещена"
```

### 📝 Безопасное логирование

```python
from agent.security import mask_sensitive_data

data = {"password": "secret123", "api_key": "sk-xxxx", "username": "admin"}
masked = mask_sensitive_data(data)
# {"password": "****", "api_key": "****", "username": "admin"}
```

### Принципы безопасности
- **Нулевое доверие к выводам LLM**: все команды валидируются через allowlist
- **Sandbox по умолчанию**: Docker Executor с минимальными привилегиями
- **Минимальные привилегии**: GitLab token только с необходимыми правами
- **Полный аудит**: каждое действие логируется с маскировкой чувствительных данных
- **Defense in Depth**: многоуровневая защита (валидация → guardrails → approval → sandbox)
## 📊 Мониторинг

### Prometheus-метрики (`:9090/metrics`)
```prometheus
# Производительность
agent_request_duration_seconds{endpoint="/api/v1/query"}
vllm_gpu_memory_utilization
qdrant_search_latency_seconds

# Качество
agent_confidence_score_bucket
error_retrieval_recall_at_5
lora_validation_answer_relevance

# Бизнес-метрики
agent_fixes_total{status="success"}
agent_autonomous_actions_total
memory_consolidation_last_timestamp
```

### Готовый дашборд Grafana
Импорт: `monitoring/dashboards/devops-agent.json`

![Дашборд: ключевые метрики](./monitoring/dashboards/preview.png)  
*(визуализация: VRAM, confidence trend, top errors, LoRA version)*

### Логи
```bash
# Просмотр в реальном времени
docker-compose logs -f agent | grep -E "(ERROR|CONFIDENCE|AUDIT)"

# Поиск по аудит-логу
jq -r 'select(.audit_id == "abc123")' ./logs/audit.jsonl

# Экспорт для анализа
docker-compose exec postgres pg_dump -U agent devops_memory -t error_cases > errors_$(date +%F).sql
```

---

## 🛠️ Troubleshooting

### Проблема: vLLM не запускается / OOM
```bash
# Проверить логи
docker-compose logs vllm | tail -50

# Уменьшить загрузку GPU
# В .env: VLLM_GPU_UTIL=0.75

# Проверить доступ к модели
ls -la /data/models/Qwen2.5-14B-Instruct-AWQ/
# Должны быть файлы: model-00001-of-00002.safetensors, config.json, tokenizer.json
```

### Проблема: Нет похожих ошибок при поиске
```bash
# Проверить индексацию в Qdrant
curl -s http://localhost:6333/collections/devops_errors/points/scroll \
  -H "Content-Type: application/json" \
  -d '{"limit": 5}' | jq

# Переиндексировать вручную
devops-agent memory consolidate --since "7d" --force

# Проверить эмбеддинги
python -c "from sentence_transformers import SentenceTransformer; 
m=SentenceTransformer('BAAI/bge-m3'); 
print(m.encode('test error', normalize_embeddings=True).shape)"
```

### Проблема: LoRA не загружается в vLLM
```bash
# Проверить структуру адаптера
ls -la ./lora_adapters/devops_v1/
# Должны быть: adapter_config.json, adapter_model.safetensors

# Проверить совместимость версий
docker-compose exec vllm python -c "import vllm; print(vllm.__version__)"
# Требуется vLLM ≥0.6.0 для dynamic LoRA

# Ручная загрузка для отладки
curl -X POST http://localhost:8000/v1/lora \
  -H "Content-Type: application/json" \
  -d '{"lora_name":"debug","lora_path":"/lora/devops_v1"}'
```

### Проблема: Агент "застревает" в цикле retry
```bash
# Проверить confidence threshold
grep CONFIDENCE_THRESHOLD .env

# Включить подробное логирование
docker-compose exec agent grep -A5 "CONFIDENCE" ./logs/agent.log

# Временно переключить в advisory mode
devops-agent ask --mode advisory --task "..."  # Только рекомендации, без выполнения
```

---

## 💡 Предложения по улучшению

### 🎯 Короткий срок (1-2 недели)
- [ ] **Webhook-интеграция с GitLab**: авто-триггер агента при падении pipeline  
  → Добавить endpoint `/webhook/gitlab` с верификацией подписи
- [ ] **Кэширование эмбеддингов**: предвычислять bge-m3 для частых ошибок  
  → Redis cache с TTL 24h, ключ: `embed:{sha256(error_signature)}`
- [ ] **Шаблоны фиксов**: библиотека проверенных решений в YAML  
  → `fixes/docker/oomkilled.yaml` с параметризованными командами
- [ ] **Экспорт в Runbook**: генерация Markdown-инструкций из успешных кейсов  
  → `devops-agent memory export --format markdown --output ./runbooks/`

### 🚀 Средний срок (1-2 месяца)
- [ ] **Мульти-модельная маршрутизация**:  
  `Qwen2.5-Coder-7B` для кода, `Qwen2.5-14B` для рассуждений, `TinyLlama` для быстрых проверок
- [ ] **Federated learning**: безопасный обмен паттернами ошибок между инстансами (без сырых данных)  
  → Гомоморфное шифрование метаданных + агрегация графов
- [ ] **Visual debugging**: интеграция с `mermaid.js` для генерации диаграмм потока ошибок  
  → `devops-agent visualize --audit-id abc123 --format mermaid`
- [ ] **Predictive alerting**: предсказание потенциальных сбоев на основе трендов в логах  
  → LSTM на метриках + триггер на превентивные действия

### 🔮 Долгосрочно (квартал+)
- [ ] **Self-improving architecture**: агент предлагает изменения в собственном коде (через MR в GitLab)  
  → Code generation + static analysis + human review workflow
- [ ] **Cross-project knowledge transfer**: обобщение паттернов между проектами (`dash-panel/backend` → `dash-panel/frontend`)  
  → Мета-обучение на уровне графа знаний
- [ ] **Offline-first sync**: работа при отключении от сети с последующей синхронизацией  
  → Local-first SQLite + CRDT для состояния
- [ ] **Formal verification**: проверка сгенерированных планов через TLA+/Coq для критических операций  
  → Интеграция с `tlaplus` или `why3`

### 🤝 Как предложить улучшение
1. Создайте ветку: `git checkout -b feature/your-idea`
2. Внесите изменения + добавьте тесты (если применимо)
3. Обновите документацию (README, .env.example)
4. Откройте Merge Request в `gitlab.dash-panel.tech/tr0jan/devops-agent`
5. Укажите: цель, тестовый сценарий, влияние на безопасность/производительность

---

## 📜 Лицензия

```
MIT License

Copyright (c) 2026 tr0jan @ dash-panel.tech

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

---

> 🛠️ **Поддержка и вопросы**  
> • Создать issue: https://gitlab.dash-panel.tech/tr0jan/devops-agent/-/issues/new  
> • Обсуждение: `#devops-ai` в внутреннем чате  
> • Документация: `docker-compose exec agent python -m pydoc -b 8081`  

*Последнее обновление: 2026-05-06*  
*Версия: 0.1.2 (alpha) — Security Hardening & Documentation Update*

### История версий

| Версия | Дата | Изменения |
|--------|------|-----------|
| 0.1.2 | 2026-05-06 | 📝 **Documentation Update**: актуализация README, исправление .env.example (удалена Markdown-разметка), полная проверка безопасности |
| 0.1.1 | 2026-05-05 | 🔐 **Security Patch**: устранены Critical и High уязвимости (Command Injection, Path Traversal, Pickle deserialization, SQL injection) |
| 0.1.0 | 2026-05-01 | 🎉 Первый альфа-релиз: базовая функциональность агента, LangGraph, vLLM, Qdrant, Neo4j |

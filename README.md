# 🤖 DevOps AI Agent — Персональный исследовательский ассистент


> **Статус**: 🟡 Активная разработка | **Обновлено**: Май 2026  
> Документ описывает высокоуровневую архитектуру, границы компонентов, потоки данных и принципы безопасности системы.

---

## 📖 Введение

DevOps-AI-Agent — это автономный ассистент для диагностики, исправления и предотвращения инцидентов в DevOps-инфраструктуре. Система построена на базе **LangGraph** (управляемый граф состояний), использует **гибридную память** (граф + вектор) и следует принципу **Zero-Trust Execution**: ни один деструктивный запрос не выполняется без валидации и явного подтверждения.

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
# 🧠 Архитектура
![shema](/img/shema.png)
# 🏗️ Схема архитектуры 

```mermaid
%%{init: {'theme': 'base', 'themeVariables': { 'primaryColor': '#1a1a2e', 'primaryTextColor': '#fff', 'primaryBorderColor': '#4a4a6a', 'lineColor': '#6a6a9a', 'secondaryColor': '#16213e', 'tertiaryColor': '#0f3460' }}}%%

graph TB
    %% ==================== ПОЛЬЗОВАТЕЛЬСКИЙ СЛОЙ ====================
    subgraph UserLayer ["👤 Пользовательский слой"]
        CLI["💻 CLI / API<br/>(ask, fix, memory)"]
        WebUI["🌐 Web UI<br/>(опционально)"]
    end

    %% ==================== ЯДРО АГЕНТА ====================
    subgraph AgentCore ["🤖 Ядро AI-агента (agent/)"]
        direction TB
        
        Main["📄 main.py<br/>Точка входа"]
        Graph["📄 graph.py<br/>LangGraph State Machine"]
        LLM["📄 llm.py<br/>LLM Provider<br/>(OpenAI / vLLM)"]
        Memory["📄 memory.py<br/>Hybrid Memory"]
        Tools["📄 tools.py<br/>DevOps Tools"]
        Schemas["📄 schemas.py<br/>Pydantic Models"]
        
        Main --> Graph
        Graph --> LLM
        Graph --> Memory
        Graph --> Tools
        Graph --> Schemas
        
        subgraph CLI_Module ["📁 cli/"]
            Ask["ask.py"]
            Fix["fix.py"]
            MemCtrl["memory.py"]
        end
        
        subgraph Security ["🔐 security/"]
            Approval["approval.py<br/>Human-in-the-Loop"]
            DockerVal["docker_validator.py<br/>Command Allowlist"]
            CypherSan["cypher_sanitizer.py<br/>Query Sanitization"]
            Secrets["secrets.py<br/>Secrets Management"]
            AuditLog["logging.py<br/>Masked Audit"]
        end
    end

    %% ==================== ИЗОЛИРОВАННЫЙ ИСПОЛНИТЕЛЬ ====================
    subgraph Executor ["🐳 docker-executor/ (Isolated)"]
        ExecAPI["📄 app.py<br/>FastAPI HTTP Endpoint"]
        ExecDocker["🐳 Docker CLI<br/>subprocess execution"]
        ExecVal["✅ Input Validation<br/>Allowlist Check"]
        
        ExecAPI --> ExecVal
        ExecVal --> ExecDocker
    end

    %% ==================== ХРАНИЛИЩА ДАННЫХ ====================
    subgraph DataLayer ["💾 Data Layer"]
        Neo4j[("🕸️ Neo4j<br/>Graph Memory<br/>- Incidents<br/>- Actions<br/>- Audit Trail")]
        Qdrant[("🎯 Qdrant<br/>Vector Store<br/>- Embeddings<br/>- Semantic Search")]
        Postgres[("🗄️ PostgreSQL<br/>Relational State<br/>- Users<br/>- Configs")]
        
        LoRA["📁 lora_adapters/<br/>devops_v1/<br/>Domain Fine-tuning"]
    end

    %% ==================== ВНЕШНИЕ СИСТЕМЫ ====================
    subgraph External ["🌍 External Systems"]
        GitLab["🔗 GitLab API<br/>(Issues, MR, CI)"]
        K8s["☸️ Kubernetes API<br/>(pods, logs, events)"]
        DockerReg["📦 Docker Registry<br/>(images, tags)"]
        WebAPI["🌐 Web APIs<br/>(docs, status pages)"]
        Slack["💬 Alert Channels<br/>(опционально)"]
    end

    %% ==================== МОНАРИНГ И БЕЗОПАСНОСТЬ ====================
    subgraph Observability ["📊 Observability"]
        Grafana["📈 Grafana Dashboards"]
        Logs["📋 Structured Logs<br/>(audit.jsonl)"]
        Guardrails["🛡️ NeMo Guardrails<br/>Prompt Injection Protection"]
    end

    %% ==================== ПОТОКИ ДАННЫХ ====================
    %% Пользователь → Агент
    CLI --> Main
    WebUI --> Main
    
    %% Агент → Безопасность
    Tools --> Approval
    Approval -->|✅ Approved| Executor
    Approval -->|❌ Rejected| AuditLog
    
    %% Агент → Хранилища
    Memory <--> Neo4j
    Memory <--> Qdrant
    Memory <--> Postgres
    
    %% Агент → Внешние системы (через инструменты)
    Tools --> GitLab
    Tools --> K8s
    Tools --> DockerReg
    Tools --> WebAPI
    
    %% Безопасность → Исполнитель
    DockerVal --> ExecAPI
    CypherSan --> Neo4j
    Secrets -.-> ExecAPI
    
    %% Исполнитель → Внешние
    ExecDocker --> K8s
    ExecDocker --> DockerReg
    
    %% Мониторинг
    AuditLog --> Logs
    Logs --> Grafana
    Guardrails --> LLM
    Guardrails --> Tools
    
    %% LoRA
    LLM -.->|Load Adapter| LoRA

    %% ==================== СТИЛИ ====================
    classDef userLayer fill:#2d3436,stroke:#636e72,color:#fff
    classDef agentCore fill:#0f3460,stroke:#4a69bd,color:#fff
    classDef executor fill:#1e272e,stroke:#485460,color:#fff
    classDef dataLayer fill:#192a56,stroke:#3c6382,color:#fff
    classDef external fill:#3d3d3d,stroke:#707070,color:#fff,dashed
    classDef observability fill:#2c2c54,stroke:#474787,color:#fff
    
    class CLI,WebUI userLayer
    class Main,Graph,LLM,Memory,Tools,Schemas,CLI_Module,Security agentCore
    class ExecAPI,ExecDocker,ExecVal executor
    class Neo4j,Qdrant,Postgres,LoRA dataLayer
    class GitLab,K8s,DockerReg,WebAPI,Slack external
    class Grafana,Logs,Guardrails observability
```

---

## 🔑 Ключевые архитектурные решения

| Решение | Обоснование | Реализация |
|---------|-------------|------------|
| **🔐 Изолированный docker-executor** | Безопасность: агент не имеет прямого доступа к `docker.sock` | HTTP API + allowlist команд + валидация входных данных |
| **🧠 Гибридная память** | Разные типы знаний требуют разных хранилищ | Neo4j (связи инцидентов), Qdrant (семантический поиск), Dict (кэш сессии) |
| **👮 Human-in-the-Loop** | Критические действия требуют подтверждения | `approval.py` блокирует `rm`, `delete`, `destroy` без явного `--force` |
| **🛡️ Guardrails на входе** | Защита от prompt injection и jailbreak | NeMo Guardrails фильтрует промпты до передачи в LLM |
| **🧵 Асинхронная архитектура** | Параллельное выполнение инструментов | `asyncio.gather()` в `tools.py` для одновременных API-запросов |
| **📦 Модульность через LangGraph** | Гибкое управление состоянием и ветвлением | Узлы графа = этапы рассуждения, рёбра = условия перехода |

---

## 🔄 Последовательность обработки запроса

```mermaid
sequenceDiagram
    participant U as 👤 Пользователь
    participant C as 💻 CLI
    participant A as 🤖 Agent Core
    participant S as 🔐 Security
    participant E as 🐳 Executor
    participant D as 💾 Data Layer
    participant X as 🌍 External
    
    U->>C: ask "почему упал pod frontend?"
    C->>A: main.py: initialize State
    A->>A: graph.py: parse_intent()
    A->>D: memory.py: retrieve_context(Neo4j+Qdrant)
    D-->>A: возвращает связанные инциденты + docs
    A->>A: llm.py: generate_plan(tools=[k8s_logs, k8s_events])
    A->>S: security/approval.py: check_action(k8s_logs)
    S-->>A: ✅ auto-approve (read-only)
    A->>E: POST /execute {"cmd": "kubectl logs..."}
    E->>E: docker_validator.py: allowlist_check()
    E->>X: kubectl → Kubernetes API
    X-->>E: возвращает логи
    E-->>A: HTTP 200 + output
    A->>A: graph.py: analyze_result()
    A->>S: audit_log(action, params, result)
    S->>D: Neo4j: CREATE (:Audit {timestamp, ...})
    A->>C: format_response("Pod упал из-за OOM...")
    C-->>U: показывает ответ + рекомендации
```

---

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
DevOps-AI-Agent/
├── 📄 .env.example                      # Шаблон переменных окружения (скопировать в .env)
├── 📄 .gitignore                        # Правила исключения файлов из Git
├── 📄 FILES.md                          # 🔍 Детальная документация по каждому файлу (91 KB)
├── 📄 LICENSE                           # Лицензия MIT
├── 📄 README.md                         # Основная документация проекта
├── 📄 docker-compose.yml                # Оркестрация: agent, neo4j, qdrant, executor, monitoring
│
├── 📁 agent/                            # 🤖 Ядро AI-агента (LangGraph + LLM)
│   ├── 📄 Dockerfile                    # Образ для контейнера агента
│   ├── 📄 requirements.txt              # Python-зависимости агента
│   ├── 📄 main.py                       # Точка входа: инициализация графа и CLI
│   ├── 📄 graph.py                      # Определение графа LangGraph (узлы, рёбра, состояние)
│   ├── 📄 llm.py                        # Конфигурация LLM-провайдеров (OpenAI/vLLM)
│   ├── 📄 memory.py                     # Работа с памятью: Neo4j + Qdrant + краткосрочная
│   ├── 📄 schemas.py                    # Pydantic-схемы: State, Input, Output, ToolResponse
│   ├── 📄 tools.py                      # Инструменты агента: shell, git, docker, k8s, web
│   │
│   ├── 📁 cli/                          # 💬 CLI-интерфейс для взаимодействия
│   │   ├── 📄 __init__.py
│   │   ├── 📄 ask.py                    # Команда `ask`: вопрос к агенту
│   │   ├── 📄 fix.py                    # Команда `fix`: анализ и исправление ошибок
│   │   └── 📄 memory.py                 # Команда `memory`: управление контекстом
│   │
│   └── 📁 security/                     # 🔐 Модуль безопасности (Human-in-the-Loop)
│       ├── 📄 __init__.py
│       ├── 📄 approval.py               # Запрос подтверждения на опасные действия
│       ├── 📄 cypher_sanitizer.py       # Валидация и санитизация Cypher-запросов
│       ├── 📄 docker_validator.py       # Allowlist Docker-команд и проверка образов
│       ├── 📄 logging.py                # Аудит-логирование с маскировкой секретов
│       └── 📄 secrets.py                # Работа с Docker Secrets и переменными окружения
│
├── 📁 config/                           # ⚙️ Конфигурация сервисов
│   ├── 📄 neo4j.conf                    # Настройки Neo4j: лимиты, логирование, plugins
│   ├── 📄 qdrant.yaml                   # Конфигурация Qdrant: коллекции, векторизация
│   └── 📁 guardrails/                   # 🛡️ NeMo Guardrails от инъекций
│       ├── 📄 config.json               # Правила и потоки диалога
│       └── 📄 rails.co                  # Коллайдер-правила для фильтрации промптов
│
├── 📁 data/                             # 💾 Данные (игнорируются в Git, монтируются в runtime)
│   ├── 📄 .gitkeep
│   └── 📁 holdout/
│       └── 📄 devops_holdout_example.jsonl  # Пример тестовых данных для валидации
│   # 📁 models/     — для fine-tuned моделей (создаётся при запуске)
│   # 📁 datasets/   — для обучающих датасетов (создаётся при запуске)
│
├── 📁 docker-executor/                  # 🐳 Изолированный сервис выполнения Docker-команд
│   ├── 📄 Dockerfile                    # Минималистичный образ с Docker CLI
│   ├── 📄 app.py                        # HTTP API: валидация → выполнение → возврат результата
│   └── 📄 requirements.txt              # Зависимости: fastapi, uvicorn, docker
│   # 🔒 Архитектура: агент → HTTP → executor → Docker (без монтирования docker.sock!)
│
├── 📁 init/                             # 🗄️ Инициализация баз данных
│   ├── 📄 01_schema.sql                 # Создание таблиц: incidents, actions, audit_trail
│   └── 📄 02_indexes.sql                # Оптимизация: GIN, B-tree, полнотекстовый поиск
│
├── 📁 logs/                             # 📋 Логи (автогенерируемые)
│   ├── 📄 .gitkeep
│   └── 📄 audit.jsonl.example           # Пример формата аудита: timestamp, action, user, result
│   # 📄 agent.log, vllm.log — создаются при запуске
│
├── 📁 lora_adapters/                    # 🎯 LoRA-адаптеры для доменной настройки LLM
│   ├── 📄 .gitkeep
│   └── 📁 devops_v1/
│       └── 📄 adapter_config.json       # Конфигурация адаптера: target_modules, r, alpha
│   # 📄 adapter_model.safetensors — загружается отдельно при обучении
│
└── 📁 monitoring/                       # 📊 Наблюдаемость
    └── 📁 dashboards/                   # Grafana-дашборды (в разработке)
        # 📄 devops-agent.json — метрики: latency, tool_usage, approval_rate, errors
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

## 🧠 Логика работы 

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

**Исправление коллизии**: Ранее агент пытался выполнять Docker-команды напрямую через subprocess, что создавало риск безопасности и дублирование логики. Теперь все команды маршрутизируются через `docker-executor` сервис с централизованной валидацией.

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

**Исправление коллизии**: Добавлена обязательная валидация всех Cypher-запросов перед выполнением через `neo4j_query()`. Раньше запросы формировались динамически без проверки, что создавало риск инъекций.

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

---

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

### История версий

| Версия | Дата | Изменения |
|--------|------|-----------|
| 0.2.0 | 2026-05-07 | 🔐 **Security & Fixes**: исправлены коллизии в Docker Executor (маршрутизация через микросервис), добавлена валидация Cypher-запросов, унифицированы переменные окружения (`LLM_API_BASE`), обновлён README с описанием исправлений |
| 0.1.2 | 2026-05-06 | 📝 **Documentation Update**: актуализация README, исправление .env.example (удалена Markdown-разметка), полная проверка безопасности |
| 0.1.1 | 2026-05-05 | 🔐 **Security Patch**: устранены Critical и High уязвимости (Command Injection, Path Traversal, Pickle deserialization, SQL injection) |
| 0.1.0 | 2026-05-01 | 🎉 Первый альфа-релиз: базовая функциональность агента, LangGraph, vLLM, Qdrant, Neo4j |

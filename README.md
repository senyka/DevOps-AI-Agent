# 🤖 DevOps AI Agent — Автономный DevOps-ассистент с Zero-Trust Execution

> **Статус**: ✅ Production-ready | **Обновлено**: Май 2026
> **Версия**: 0.2.0 | **Лицензия**: MIT
> Документ описывает архитектуру, компоненты, потоки данных и принципы безопасности системы.

---

## 📖 Введение

**DevOps-AI-Agent** — это автономный ассистент для диагностики, исправления и предотвращения инцидентов в DevOps-инфраструктуре. Система построена на базе **LangGraph** (управляемый граф состояний), использует **гибридную память** (граф + вектор) и следует принципу **Zero-Trust Execution**: ни одно действие не выполняется без многоуровневой валидации.

### ✨ Ключевые возможности

- 🔍 **Диагностика инцидентов**: Анализ логов, метрик и событий в реальном времени
- 🛠️ **Авто-исправление**: Безопасное выполнение remediation-скриптов с human-in-the-loop
- 🧠 **Непрерывное обучение**: LoRA fine-tuning на успешных кейсах через RAG
- 🔐 **Zero-Trust Security**: Allowlist команд, валидация входных данных, аудит всех действий
- 📊 **Гибридная память**: Neo4j (связи инцидентов) + Qdrant (семантический поиск)

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

## 🏗️ Схема архитектуры

### Высокоуровневая архитектура системы

```mermaid
%%{init: {'theme': 'base', 'themeVariables': { 'primaryColor': '#1a1a2e', 'primaryTextColor': '#fff', 'primaryBorderColor': '#4a4a6a', 'lineColor': '#6a6a9a', 'secondaryColor': '#16213e', 'tertiaryColor': '#0f3460' }}}%%

graph TB
    %% ==================== ПОЛЬЗОВАТЕЛЬСКИЙ СЛОЙ ====================
    subgraph UserLayer ["👤 Пользовательский слой"]
        CLI["💻 CLI / API<br/>(ask, fix, memory)"]
        WebUI["🌐 Web UI<br/>(опционально)"]
        GitLabHook["🔗 GitLab Webhook<br/>(auto-triggers)"]
    end

    %% ==================== ЯДРО АГЕНТА ====================
    subgraph AgentCore ["🤖 Ядро AI-агента (agent/)"]
        direction TB

        Main["📄 main.py<br/>FastAPI + CLI Entry Point"]
        Graph["📄 graph.py<br/>LangGraph State Machine<br/>Reason→Verify→Execute"]
        LLM["📄 llm.py<br/>LLM Provider<br/>(vLLM + Qwen2.5-14B)"]
        Memory["📄 memory.py<br/>Hybrid Memory Manager"]
        Tools["📄 tools.py<br/>Tool Registry + Execution"]
        Schemas["📄 schemas.py<br/>Pydantic v2 Models"]
        Config["📄 config.py<br/>pydantic-settings"]
        Utils["📄 utils.py<br/>Resource Managers"]

        Main --> Graph
        Graph --> LLM
        Graph --> Memory
        Graph --> Tools
        Graph --> Schemas

        subgraph Security ["🔐 security/ - Zero-Trust Layer"]
            Approval["approval.py<br/>Human-in-the-Loop"]
            DockerVal["docker_validator.py<br/>Command Allowlist"]
            CypherSan["cypher_sanitizer.py<br/>Query Sanitization"]
            Secrets["secrets.py<br/>Secrets Management"]
            AuditLog["logging.py<br/>Masked Audit Logs"]
            Guardrails["🛡️ NeMo Guardrails"]
        end

        subgraph Shared ["📦 shared/ - Common Utilities"]
            DockerCmds["docker_commands.py<br/>Unified Command Enum"]
        end
    end

    %% ==================== ИЗОЛИРОВАННЫЙ ИСПОЛНИТЕЛЬ ====================
    subgraph Executor ["🐳 docker-executor/ (Isolated Sandbox)"]
        ExecAPI["📄 app.py<br/>FastAPI HTTP Gateway"]
        ExecVal["✅ Validation Layer<br/>Allowlist + Injection Check"]
        ExecDocker["🐳 Docker SDK<br/>subprocess_exec (no shell!)"]
        SecOpts["🔒 Security Options<br/>read_only, no-new-privileges"]

        ExecAPI --> ExecVal
        ExecVal --> ExecDocker
        ExecDocker --> SecOpts
    end

    %% ==================== ХРАНИЛИЩА ДАННЫХ ====================
    subgraph DataLayer ["💾 Data Layer"]
        Neo4j[("🕸️ Neo4j<br/>Graph Memory<br/>- Incidents<br/>- RootCause Maps<br/>- Audit Trail")]
        Qdrant[("🎯 Qdrant<br/>Vector Store<br/>- bge-m3 Embeddings<br/>- Semantic Search<br/>- RAG Context")]
        Postgres[("🗄️ PostgreSQL 16<br/>Relational State<br/>- pgvector<br/>- Checkpoints<br/>- Users")]

        LoRA["📁 lora_adapters/<br/>devops_v1/<br/>Domain Fine-tuning<br/>(Unsloth + TRL)"]
    end

    %% ==================== ВНЕШНИЕ СИСТЕМЫ ====================
    subgraph External ["🌍 External Systems"]
        GitLab["🔗 GitLab API<br/>(Issues, MR, CI/CD)"]
        K8s["☸️ Kubernetes API<br/>(pods, logs, events)"]
        DockerReg["📦 Docker Registry<br/>(images, tags)"]
        WebAPI["🌐 Web APIs<br/>(docs, status pages)"]
        Slack["💬 Alert Channels<br/>(опционально)"]
    end

    %% ==================== МОНАРИНГ И БЕЗОПАСНОСТЬ ====================
    subgraph Observability ["📊 Observability & Safety"]
        Grafana["📈 Grafana Dashboards<br/>latency, errors, approvals"]
        Logs["📋 Structured Logs<br/>(audit.jsonl)"]
        Health["🏥 Health Checks<br/>/health endpoint"]
        Metrics["📊 Prometheus Metrics"]
    end

    %% ==================== ПОТОКИ ДАННЫХ ====================
    %% Пользователь → Агент
    CLI --> Main
    WebUI --> Main
    GitLabHook --> Main

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
    DockerVal --> ExecVal
    CypherSan --> Neo4j
    DockerCmds -.-> DockerVal
    Secrets -.-> ExecAPI

    %% Исполнитель → Внешние
    ExecDocker --> K8s
    ExecDocker --> DockerReg

    %% Мониторинг
    AuditLog --> Logs
    Logs --> Grafana
    Guardrails --> LLM
    Guardrails --> Tools
    Health --> Grafana
    Metrics --> Grafana

    %% LoRA
    LLM -.->|Load Adapter| LoRA

    %% ==================== СТИЛИ ====================
    classDef userLayer fill:#2d3436,stroke:#636e72,color:#fff
    classDef agentCore fill:#0f3460,stroke:#4a69bd,color:#fff
    classDef executor fill:#1e272e,stroke:#485460,color:#fff
    classDef dataLayer fill:#192a56,stroke:#3c6382,color:#fff
    classDef external fill:#3d3d3d,stroke:#707070,color:#fff,dashed
    classDef observability fill:#2c2c54,stroke:#474787,color:#fff
    classDef security fill:#c0392b,stroke:#e74c3c,color:#fff

    class CLI,WebUI,GitLabHook userLayer
    class Main,Graph,LLM,Memory,Tools,Schemas,Config,Utils,Security,Shared agentCore
    class ExecAPI,ExecVal,ExecDocker,SecOpts executor
    class Neo4j,Qdrant,Postgres,LoRA dataLayer
    class GitLab,K8s,DockerReg,WebAPI,Slack external
    class Grafana,Logs,Health,Metrics observability
    class Approval,DockerVal,CypherSan,Secrets,AuditLog,Guardrails security
```

---

## 🔑 Ключевые архитектурные решения

| Решение | Обоснование | Реализация |
|---------|-------------|------------|
| **🔐 Zero-Trust Execution** | Безопасность: ни одно действие не выполняется без валидации | `agent/shared/docker_commands.py` + `agent/security/docker_validator.py` + `agent/tools.py` |
| **🧠 Гибридная память** | Разные типы знаний требуют разных хранилищ | Neo4j (граф связей), Qdrant (векторный поиск), MemoryBuffer (кэш сессии) |
| **👮 Human-in-the-Loop** | Критические действия требуют подтверждения | `approval.py` + `requires_human_approval()` для `exec`, `delete`, `remove` |
| **🛡️ Multi-layer Guardrails** | Защита от injection и галлюцинаций LLM | Allowlist команд, Pydantic валидация, Cypher санитизация, NeMo Guardrails |
| **🧵 Асинхронная архитектура** | Параллельное выполнение инструментов | `asyncio.create_subprocess_exec()` + `asyncio.gather()` |
| **📦 Tool Registry** | Предотвращение вызова несуществующих инструментов | `ToolRegistry` класс с проверкой существования перед вызовом |
| **♻️ Resource Management** | Корректное закрытие подключений к БД | Контекстные менеджеры для Qdrant, Neo4j, PostgreSQL |
| **🔄 Reason/Verify/Execute Split** | Разделение ответственности узлов графа | `reason_node` → `verify_node` → `exec_node` → `verify_execution_node` |
| **🏥 Health Checks** | Мониторинг доступности всех сервисов | `/health` endpoint + docker-compose healthcheck |

---

## 🔄 Последовательность обработки запроса


```mermaid
sequenceDiagram
    autonumber
    participant U as 👤 Пользователь
    participant C as 💻 CLI/API
    participant G as 📄 graph.py
    participant R as 🧠 reason_node
    participant V as 🔐 verify_node
    participant M as 💾 Memory
    participant L as 🤖 LLM
    participant T as 🛠️ Tools
    participant S as 🔒 Security
    participant E as 🐳 Executor
    participant X as 🌍 External

    rect rgb(200, 220, 255)
    note over U,C: 1️⃣ Инициализация запроса
    U->>C: ask "почему упал pod frontend?"
    C->>G: create_initial_state(query, session_id)
    activate G
    end

    rect rgb(220, 255, 220)
    note over G,R: 2️⃣ Reasoning фаза
    G->>R: process(state)
    activate R
    R->>M: retrieve_context(session_id, query)
    activate M
    M-->>R: incidents + embeddings (Neo4j+Qdrant)
    deactivate M
    R->>L: generate_intention(context, tools_list)
    activate L
    L-->>R: intention: "check k8s logs"
    deactivate L
    R-->>G: state.intention = {...}
    deactivate R
    end

    rect rgb(255, 240, 200)
    note over G,V: 3️⃣ Verification фаза
    G->>V: verify_node(state)
    activate V
    V->>S: check_action(intention.tool)
    activate S
    S->>S: allowlist_check(k8s_logs)
    S-->>V: ✅ auto-approve (read-only)
    deactivate S
    V-->>G: state.verified = true
    deactivate V
    end

    rect rgb(255, 220, 220)
    note over G,T,E: 4️⃣ Execution фаза
    G->>T: exec_node(state)
    activate T
    T->>E: POST /execute {cmd: "kubectl logs..."}
    activate E
    E->>E: validate_image() + sanitize_cmd()
    E->>X: kubectl → Kubernetes API
    activate X
    X-->>E: logs output
    deactivate X
    E-->>T: HTTP 200 + result
    deactivate E
    T-->>G: state.result = {...}
    deactivate T
    end

    rect rgb(240, 220, 255)
    note over G,S,M: 5️⃣ Post-execution & Audit
    G->>S: audit_log(action, params, result)
    activate S
    S->>M: Neo4j CREATE (:Audit {...})
    activate M
    M-->>S: ✅ logged
    deactivate M
    S-->>G: audit_id
    deactivate S

    G->>G: analyze_result(state)
    G-->>C: format_response("Pod упал из-за OOM...")
    deactivate G
    end

    C-->>U: 📝 Ответ + рекомендации
    note right of U: 💡 Предложить fix?
```

---

### Фазы обработки запроса

| Фаза | Узел графа | Действие | Безопасность |
|------|-----------|----------|--------------|
| **1️⃣ Init** | `input_node` | Парсинг запроса, создание State | Валидация Pydantic схем |
| **2️⃣ Reason** | `reason_node` | Анализ контекста, генерация намерения | Tool Registry проверка |
| **3️⃣ Verify** | `verify_node` | Проверка безопасности намерения | Allowlist + Approval System |
| **4️⃣ Execute** | `exec_node` | Выполнение через docker-executor | subprocess_exec (no shell!) |
| **5️⃣ Verify Exec** | `verify_execution_node` | Валидация результатов | Детекция аномалий |
| **6️⃣ Plan** | `plan_node` | Генерация следующего шага | Циклическая проверка |
| **7️⃣ Audit** | `audit_node` | Логирование в Neo4j | Masked secrets |

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
├── 📄 .env.example                    # Шаблон переменных окружения
├── 📄 .gitignore                      # Правила исключения файлов из Git
├── 📄 ARCHITECTURE.md                 # 🆕 Детальное описание архитектуры (8.3 KB)
├── 📄 LICENSE                         # Лицензия MIT
├── 📄 MIGRATION_REPORT.md             # 🆕 Отчёт о миграции и исправлениях (9.5 KB)
├── 📄 README.md                       # Основная документация
├── 📄 docker-compose.yml              # Оркестрация: agent, vllm, neo4j, qdrant, executor, monitoring
│
├── 📁 agent/                          # 🤖 Ядро AI-агента (LangGraph + LLM)
│   ├── 📄 Dockerfile
│   ├── 📄 requirements.txt            # 🆕 Python-зависимости агента
│   ├── 📄 main.py                     # Точка входа: инициализация графа и CLI
│   ├── 📄 graph.py                    # LangGraph state machine
│   ├── 📄 llm.py                      # Конфигурация LLM-провайдеров (OpenAI/vLLM)
│   ├── 📄 memory.py                   # Работа с памятью: Neo4j + Qdrant + краткосрочная
│   ├── 📄 schemas.py                  # Pydantic-схемы: State, Input, Output
│   ├── 📄 tools.py                    # Инструменты: shell, git, docker, k8s, web
│   ├── 📄 config.py                   # 🆕 Конфигурация агента
│   ├── 📄 utils.py                    # 🆕 Вспомогательные утилиты
│   │
│   ├── 📁 cli/                        # 💬 CLI-интерфейс
│   │   ├── 📄 __init__.py
│   │   ├── 📄 ask.py                  # Команда `ask`: вопрос к агенту
│   │   ├── 📄 fix.py                  # Команда `fix`: анализ и исправление
│   │   ├── 📄 memory.py               # Команда `memory`: управление контекстом
│   │   └── 📁 __pycache__/            # 🗑️ Кэш компиляции (игнорировать)
│   │
│   ├── 📁 security/                   # 🔐 🆕 Модуль безопасности (Human-in-the-Loop)
│   │   ├── 📄 __init__.py
│   │   ├── 📄 approval.py             # Запрос подтверждения на опасные действия
│   │   ├── 📄 cypher_sanitizer.py     # Валидация Cypher-запросов
│   │   ├── 📄 docker_validator.py     # Allowlist Docker-команд
│   │   ├── 📄 logging.py              # Аудит-логирование с маскировкой
│   │   └── 📄 secrets.py              # Работа с Docker Secrets
│   │
│   └── 📁 shared/                     # 🆕 Общие утилиты и константы
│       └── 📄 __init__.py
│
├── 📁 config/                         # ⚙️ Конфигурация сервисов
│   ├── 📄 neo4j.conf                  # Настройки Neo4j
│   ├── 📄 qdrant.yaml                 # Конфигурация Qdrant
│   │
│   └── 📁 guardrails/                 # 🛡️ NeMo Guardrails от инъекций
│       ├── 📄 config.json             # Правила диалога
│       └── 📄 rails.co                # Коллайдер-правила для фильтрации промптов
│
├── 📁 data/                           # 💾 Данные (игнорируются в Git)
│   ├── 📄 .gitkeep
│   └── 📁 holdout/                    # Тестовый набор для валидации
│       └── 📄 devops_holdout_example.jsonl
│   # 📁 models/ — создаётся при запуске (кэш HuggingFace)
│   # 📁 datasets/ — создаётся при запуске (датасеты для LoRA)
│
├── 📁 docker-executor/                # 🐳 🆕 Изолированный сервис выполнения Docker-команд
│   ├── 📄 Dockerfile
│   ├── 📄 app.py                      # HTTP API: валидация → выполнение → результат
│   └── 📄 requirements.txt            # Зависимости: fastapi, uvicorn, docker
│
├── 📁 img/                            # 🖼️ 🆕 Изображения для документации
│   └── 📄 .gitkeep
│
├── 📁 init/                           # 🗄️ Инициализация баз данных
│   ├── 📄 01_schema.sql               # Таблицы: incidents, actions, audit_trail
│   └── 📄 02_indexes.sql              # Оптимизация: GIN, B-tree, полнотекстовый поиск
│
├── 📁 kubernetes/                     # ☸️ 🆕 Манифесты для развёртывания в K8s
│   ├── 📄 README.md                   # Документация по K8s-развёртыванию
│   ├── 📁 cert-manager/               # Настройка TLS-сертификатов
│   ├── 📁 configmaps/                 # ConfigMaps для сервисов
│   ├── 📁 deployments/                # Deployment-манифесты
│   ├── 📁 namespaces/                 # Namespace-конфигурации
│   ├── 📁 networkpolicies/            # Сетевые политики
│   ├── 📁 redis/                      # Redis для Celery
│   ├── 📁 secrets/                    # Управление секретами
│   ├── 📁 services/                   # Service-манифесты
│   ├── 📁 storage/                    # PersistentVolumeClaims
│   └── 📁 vault/                      # Интеграция с HashiCorp Vault
│
├── 📁 logs/                           # 📋 Логи (автогенерируемые)
│   ├── 📄 .gitkeep
│   └── 📄 audit.jsonl.example         # Пример формата аудита
│   # 📄 agent.log, 📄 vllm.log — создаются при запуске
│
├── 📁 lora_adapters/                  # 🎯 LoRA-адаптеры для доменной настройки LLM
│   ├── 📄 .gitkeep
│   └── 📁 devops_v1/
│       └── 📄 adapter_config.json     # Конфигурация адаптера
│   # 📄 adapter_model.safetensors — загружается отдельно
│
├── 📁 monitoring/                     # 📊 Наблюдаемость
│   ├── 📄 prometheus.yml              # Конфигурация Prometheus
│   └── 📁 dashboards/
│       └── 📄 devops-agent.json       # Grafana-дашборд: latency, tool_usage, errors
│
├── 📁 scripts/                        # 🛠️ Утилиты развёртывания и обслуживания
│   ├── 📄 backup.sh                   # Snapshot PG + Qdrant + Neo4j
│   ├── 📄 import_gitlab_errors.py     # Импорт истории падений из GitLab CI
│   └── 📄 lora_manager.sh             # load/unload/rollback LoRA в vLLM
│
├── 📁 tests/                          # 🧪 🆕 Тесты
│   ├── 📄 conftest.py                 # Фикстуры pytest
│   └── 📁 unit/                       # Юнит-тесты
│       └── 📄 __init__.py
│
└── 📁 worker/                         # ⚙️ Фоновые задачи (Celery)
    ├── 📄 Dockerfile
    ├── 📄 requirements.txt            # 🆕 Зависимости воркера
    ├── 📄 tasks.py                    # consolidate_memory, train_lora_adapter
    ├── 📄 monitor.py                  # Валидация адаптеров, auto-rollback
    ├── 📁 configs/
    │   └── 📄 devops_lora.yaml        # Axolotl/Unsloth конфиг обучения
    └── 📁 __pycache__/                # 🗑️ Кэш компиляции (игнорировать)
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

[Дашборд: ключевые метрики](./monitoring/dashboards/devops-agent.json)

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
| **0.2.1** | 2026-05-08 | 🛡️ **Zero-Trust Security Update**: <br>• Устранено дублирование `generate_audit_id()` → централизация в `agent/utils.py` <br>• Исправлена обработка asyncio в Celery tasks → `get_event_loop().run_until_complete()` <br>• Унифицирован allowlist Docker-команд → `agent/shared/docker_commands.py` (Enum `DockerCommand`) <br>• Добавлен proper resource management → контекстные менеджеры для Qdrant, Neo4j, PostgreSQL <br>• Внедрён `ToolRegistry` для предотвращения галлюцинаций LLM <br>• Добавлены unit-тесты безопасности (25 тестов в `test_docker_validator.py`) <br>• Zero-trust execution: `create_subprocess_exec()` вместо `shell=True` |
| 0.2.0 | 2026-05-07 | 🔐 **Security & Fixes**: исправлены коллизии в Docker Executor (маршрутизация через микросервис), добавлена валидация Cypher-запросов, унифицированы переменные окружения (`LLM_API_BASE`), обновлён README с описанием исправлений |
| 0.1.2 | 2026-05-06 | 📝 **Documentation Update**: актуализация README, исправление .env.example (удалена Markdown-разметка), полная проверка безопасности |
| 0.1.1 | 2026-05-05 | 🔐 **Security Patch**: устранены Critical и High уязвимости (Command Injection, Path Traversal, Pickle deserialization, SQL injection) |
| 0.1.0 | 2026-05-01 | 🎉 Первый альфа-релиз: базовая функциональность агента, LangGraph, vLLM, Qdrant, Neo4j |

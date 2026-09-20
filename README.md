# Telegram AI Bot with Semantic Memory

Telegram AI assistant with:
- 🧠 **Long-Term Semantic Memory**: Continuous fact extraction, vector indexing, and automatic deduplication.
- 🔍 **Vector Search (Gemini Embeddings)**: 3072-dimensional embeddings (`gemini-embedding-2`) with calibrated cosine similarity retrieval.
- ⚡ **Asynchronous Extraction Pipeline**: Zero-latency Telegram message ingest; facts extracted in background workers.
- 🛡️ **Zero Cross-User Context Bleed**: Strict database-level isolation (`messages.user_id` JOIN) preventing multi-user memory collisions.
- 🔀 **Recursive Context Assembly**: SQL CTE reply chains (`WITH RECURSIVE`) up to 10 levels deep for multi-party thread continuity.
- 📊 **Production-Tuned & Audited**: Real-time LLM cost tracking, token guards, and self-healing worker architectures.

---

## 📊 Results & Production Metrics

| Metric | Result | Impact |
| :--- | :--- | :--- |
| **Indexed Memory Base** | **1,600+ chunks** | Live personal and contextual knowledge base in production |
| **Search Latency** | **< 300 ms** | Fast in-memory NumPy matrix cosine similarity ranking |
| **Vector Geometry** | **3072 dimensions** | High-fidelity representations via Google `gemini-embedding-2` |
| **Ingestion Overhead** | **0 ms (async queue)** | High-throughput Telegram loop 100% decoupled from LLM latency |
| **Recall / Noise Rejection**| **100% / 100%** | Optimal score threshold (`0.60`) eliminates hallucinations and noise |

---

## 🏗️ Architecture

```mermaid
flowchart TD
    subgraph Telegram Ingestion
        TG[Telegram API] -->|New Message| Ingest[Aiogram 3 Polling Handler]
        Ingest -->|1. Store Raw Message| DB_Msg[(PostgreSQL: messages)]
        Ingest -->|2. Enqueue Job| DB_Jobs[(PostgreSQL: embedding_jobs)]
        Ingest -->|3. Immediate ACK| TG
    end

    subgraph Asynchronous Memory Pipeline
        DB_Jobs -.->|Poll pending| Worker[Embedding Worker]
        Worker -->|Fact Classification| FlashLLM[Gemini Flash Lite]
        FlashLLM -->|Noise Filter| Filter{Is Fact?}
        Filter -->|NO_MEMORY| Complete[Mark Job Completed]
        Filter -->|Atomic Fact| Embed[Gemini Embedding 2: 3072-dim]
        Embed --> Dedup{User-Isolated Dedup}
        Dedup -->|Duplicate for User| Skip[Skip Chunk]
        Dedup -->|New Unique Fact| SaveChunk[(PostgreSQL: memory_chunks)]
    end

    subgraph Hybrid Context Retrieval
        UserQuery[User Query / Mention] --> CB[Context Builder]
        CB -->|Recursive SQL CTE| Thread[Reply Chain Context]
        CB -->|Recent 15 msgs| History[Short-Term Group Context]
        CB -->|Cosine Sim >= 0.60| Search[User-Isolated Memory Search]
        SaveChunk -.-> Search
        Thread & History & Search --> TokenGuard[Token Budget & Guard]
        TokenGuard --> FinalPrompt[Synthesized Context Bundle]
        FinalPrompt --> Gemini[Gemini Chat Model]
        Gemini --> Response[Telegram Response]
    end
```

---

## 💡 Interesting Engineering Challenges & Solutions

### 1. Semantic Deduplication & Cross-User Isolation Collision
* **The Problem**: The initial semantic deduplicator checked cosine similarity across all existing chunks in `memory_chunks` globally. When User A recorded a fact (e.g. *"I am a Python developer"*), User B with the same fact had their memory rejected as a duplicate.
* **The Solution**: Re-architected `EmbeddingRepository.is_semantic_duplicate` to enforce an inner join with `messages` scoped to `messages.user_id == user_id`.
* **Production Evidence**: On the live production database with existing chunks, identical vectors return `True` for the original author and `False` for different users, completely preventing cross-tenant memory blockage.

### 2. Similarity Threshold Calibration: The 0.70 vs 0.60 Discovery
* **The Problem**: Conventional rule-of-thumb thresholds (`0.70`) caused a **66% false negative rate** on factual queries. Crucial personal facts scored just below the cutoff (*"Where did I study?"* $\to$ `0.637`, *"Which city do I live in?"* $\to$ `0.614`), leading to false bot amnesia.
* **The Solution**: Conducted similarity distribution sweeps across production queries:
  - Factual questions mapped to the `0.61 – 0.75` similarity band.
  - Conversational noise (*"hello"*, *"what is the weather"*) mapped strictly below `0.45`.
  - Calibrating `MEMORY_MIN_SCORE=0.60` yielded **100% recall on target facts with 0% noise bleed**.

### 3. Decoupled Asynchronous Fact Extraction Pipeline
* **The Problem**: Evaluating messages with an LLM during the Telegram webhook/polling cycle added 800–1500 ms latency per message and invited rate limits (HTTP 429).
* **The Solution**: Designed an asynchronous persistent job queue in PostgreSQL (`embedding_jobs`). Telegram handlers acknowledge messages in `< 5ms`. Background workers consume jobs, invoke fact extraction with structured JSON schemas, and back off gracefully on quota exhaustion.

### 4. Production Incident Debugging: Variable Scope & Queue Healing
* **The Problem**: A variable scoping bug (`NameError: name 'chat_id' is not defined`) in `embedding_worker.py` silently stalled background extraction jobs, accumulating 47 unprocessed queue items.
* **The Solution**: Diagnosed via production log analysis, fixed variable resolution (`msg_chat_id` / `msg_user_id`), reset failed job attempts, and reprocessed all 47 items in production without data loss. Added health probes and `journalctl` error audit checks.

### 5. Context Window Inflation & Recursive Reply Chains
* **The Problem**: In active group chats with multiple simultaneous threads, passing the last $N$ chronological messages confused the LLM and bloated token costs.
* **The Solution**: Implemented a recursive SQL CTE (`WITH RECURSIVE`) that traverses `reply_to_message_id` pointers up to 10 levels deep, assembling the exact dialogue tree while maintaining strict token limits.

---

## 🛠️ Key Capabilities

- **Isolated Identity Query Routing**: Dedicated routing for *"Who am I?"* or *"What do you know about me?"* queries that injects up to 10 verified personal memories while zeroing out group chat noise.
- **Forwarded Message Attribution**: Metadata extractor records the original author and channel of forwarded messages, preventing "Ghost Authorship" hallucinations.
- **Real-Time LLM Cost & Latency Accounting**: Every LLM interaction logs input/output tokens, latency in ms, and calculated USD cost to `llm_logs`.
- **Prompt Injection Defense**: Security heuristics inspect inputs before retrieval to prevent adversarial memory tampering.

---

## 💻 Tech Stack

- **Core**: Python 3.10+, Aiogram 3.3 (Telegram Bot Framework)
- **Database & Vectors**: PostgreSQL 15, `pgvector`, SQLAlchemy 2.0 (Asyncio), Alembic
- **LLM & Embeddings**: Google Gemini API (`google-genai` SDK), `gemini-embedding-2` (3072 dims), `gemini-2.5-flash`
- **Vector Operations**: NumPy matrix operations (Cosine Similarity, L2 normalization)
- **Infrastructure**: Systemd process management, Docker Compose, Linux VPS

---

## 📂 Repository Structure

```text
├── app/
│   ├── ai/                  # LLM service abstraction, token guard, prompt builders
│   ├── bot/                 # Aiogram routers, command handlers, health server
│   ├── database/            # Async SQLAlchemy engine, models, repositories
│   │   ├── models/          # User, Chat, Message, MemoryChunk, EmbeddingJob, LlmLog
│   │   └── repositories/    # MessageRepository, EmbeddingRepository, UserRepository
│   ├── memory/              # Vector store, embedding service, context builder
│   ├── services/            # Media intelligence, message processing pipeline
│   └── workers/             # Background embedding & fact extraction worker
├── config/                  # Configuration schema & defaults
├── docs/                    # Architecture records, decisions, and problem logs
│   ├── ARCHITECTURE.md      # Detailed system data flow and design choices
│   ├── DECISIONS.md         # Architecture Decision Records (ADRs)
│   └── PROBLEMS.md          # Troubleshooting and resolution log
├── migrations/              # Alembic database migration scripts
├── scripts/                 # Maintenance, migration, and backup utilities
├── tests/                   # Unit, integration, and prompt injection test suites
├── alembic.ini              # Migration environment config
├── docker-compose.yml       # Local PostgreSQL + pgvector container definition
├── requirements.txt         # Production dependencies
└── .env.example             # Clean environment variable template
```

---

## 🚀 Quick Start

### 1. Installation
```bash
git clone https://github.com/MOneK292/chatbot-showcase.git
cd chatbot-showcase

python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Environment Setup
```bash
cp .env.example .env
```
Populate `.env` with your credentials:
```env
TELEGRAM_BOT_TOKEN="your-telegram-bot-token"
GEMINI_API_KEY="your-gemini-api-key"
DATABASE_URL="postgresql+psycopg://user:password@localhost:5432/chatbot"
MEMORY_MIN_SCORE=0.60
IDENTITY_MEMORY_TOP_K=10
```

### 3. Migrations & Running
```bash
# Run migrations
alembic upgrade head

# Start Telegram bot
python -m app.main

# In another terminal, start the embedding worker
python -m app.workers.embedding_worker
```

---

## 📄 License
MIT License. Free for educational, research, and showcase purposes.

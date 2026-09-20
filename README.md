# 🤖 Telegram AI Bot with Long-Term Semantic Memory

Production-ready, multi-tenant Telegram AI Bot architecture featuring a **multi-level hybrid memory pipeline**, asynchronous fact extraction, vector similarity search, and strict user-level context isolation.

---

## 🌟 Key Architecture & Capabilities

### 1. 🧠 Multi-Tier Hybrid Memory Engine
- **Active Fact Extraction**: User messages pass through an asynchronous background worker that extracts atomic personal and contextual facts while discarding conversational noise (`NO_MEMORY`).
- **Semantic Deduplication**: Uses cosine similarity with vector clustering. Ensures that similar facts are deduplicated per user without bleeding across different chat participants.
- **Calibrated Semantic Retrieval**: Optimized cosine similarity threshold (`MEMORY_MIN_SCORE=0.60`) prevents hallucinations and conversational drift while capturing relevant biographical facts.
- **Isolated Identity Query Handling**: Dedicated query-routing for self-referential queries (*"Who am I?"*, *"What do you remember about me?"*) delivering up to 10 verified personal facts with zero group-chat noise.

### 2. 🔀 Recursive Reply Chain (SQL CTE)
- Retrieves entire threads and conversation branches up to 10 levels deep using recursive SQL Common Table Expressions (`WITH RECURSIVE`).
- Preserves context across parallel discussions in busy group chats without confusing interlocutors.

### 3. 🛡️ User Privacy & Context Bleed Prevention
- Strict per-user isolation at database query level (`messages.user_id` joined with `memory_chunks`).
- Forwarded message intelligence preserving original sender attribution without assigning external quotes to the current user.

### 4. ⚡ High-Throughput Ingestion
- Telegram event loop is never blocked by LLM calls.
- Messages are immediately persisted into PostgreSQL; embedding and summarization jobs are queued and processed asynchronously.

---

## 🏗️ Architecture Overview

```mermaid
flowchart TD
    TG[Telegram API] --> Ingest[Aiogram 3 Ingestion]
    Ingest --> DB[(PostgreSQL + pgvector)]
    Ingest --> Reply[Reply Chain CTE]
    
    DB -.-> JobQueue[Embedding Jobs Table]
    JobQueue --> Worker[Embedding Worker]
    Worker --> LLMExtract[Fact Extraction]
    LLMExtract --> Dedup{Semantic Dedup per User}
    Dedup -->|Unique| MemoryStore[(Memory Chunks)]
    Dedup -->|Duplicate| Skip[Discard Duplicate]
    
    UserQuery[User Message] --> ContextBuilder[Context Builder]
    ContextBuilder --> Reply
    ContextBuilder --> ShortTerm[Recent 15 Messages]
    ContextBuilder --> VectorSearch[Cosine Vector Search]
    MemoryStore --> VectorSearch
    
    ContextBuilder --> LLM[Google Gemini LLM]
    LLM --> Response[Telegram Response]
```

---

## 📂 Project Structure

```text
├── app/
│   ├── bot/                 # Aiogram 3 bot setup, routers, handlers, health check
│   ├── database/            # SQLAlchemy models, async session, repository pattern
│   │   ├── models/          # User, Chat, Message, MemoryChunk, EmbeddingJob, LlmLog
│   │   └── repositories/    # MessageRepository, EmbeddingRepository
│   ├── memory/              # Memory engine: vector store, embedding service, context builder
│   ├── services/            # LLM service abstraction, message processing
│   └── workers/             # Background embedding & fact extraction worker
├── config/                  # Application configuration templates
├── migrations/              # Alembic database migrations
├── prompts/                 # Prompt definitions for memory extraction and persona
├── scripts/                 # Maintenance, migration, and backup utilities
├── tests/                   # Unit, integration, and prompt injection test suites
├── alembic.ini              # Database migration configuration
├── docker-compose.yml       # Local development stack (PostgreSQL + pgvector)
├── requirements.txt         # Production dependencies
└── .env.example             # Environment variable template
```

---

## 🚀 Quick Start

### 1. Prerequisites
- Python 3.10+
- PostgreSQL 14+ with `pgvector` extension
- Telegram Bot Token (from [@BotFather](https://t.me/BotFather))
- Google Gemini API Key

### 2. Installation

Clone the repository and install dependencies:
```bash
git clone https://github.com/MOneK292/chatbot-showcase.git
cd chatbot-showcase

python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Configuration

Copy `.env.example` and set your configuration parameters:
```bash
cp .env.example .env
```

Key environment variables:
```env
TELEGRAM_BOT_TOKEN="your-bot-token"
GEMINI_API_KEY="your-gemini-api-key"
DATABASE_URL="postgresql+psycopg://user:password@localhost:5432/chatbot"

# Memory & Retrieval Tuning
MEMORY_MIN_SCORE=0.60
MEMORY_CONTEXT_TOP_K=5
IDENTITY_MEMORY_TOP_K=10
```

### 4. Database Setup & Migrations

Run database migrations using Alembic:
```bash
alembic upgrade head
```

### 5. Running the Application

Start the main bot process:
```bash
python -m app.main
```

In a separate process, start the background embedding worker:
```bash
python -m app.workers.embedding_worker
```

---

## 🧪 Testing

Run the test suite using pytest:
```bash
pytest tests/
```

---

## 📄 License
MIT License. Free for educational, research, and commercial showcase use.

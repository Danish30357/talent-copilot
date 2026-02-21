# 🧠 TalentCopilot

**Enterprise-grade, multi-tenant AI recruiting assistant platform.**

Built with FastAPI · LangChain · LangGraph · PostgreSQL · Celery · Streamlit

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Streamlit Frontend                        │
│   Chat UI · Confirmation Modal · CV Upload · Job Polling    │
└──────────────────────────┬──────────────────────────────────┘
                           │ HTTP / JWT
┌──────────────────────────▼──────────────────────────────────┐
│                   FastAPI Backend                            │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ Presentation Layer    Auth · Chat · Confirmations     │   │
│  │                       Jobs · Workspace                │   │
│  ├──────────────────────────────────────────────────────┤   │
│  │ Application Layer     ChatService · ConfirmationSvc  │   │
│  │                       MemoryService · JobService      │   │
│  │                       ToolService                     │   │
│  ├──────────────────────────────────────────────────────┤   │
│  │ Domain Layer          Entities · Enums · Interfaces   │   │
│  │                       Exceptions                      │   │
│  ├──────────────────────────────────────────────────────┤   │
│  │ Infrastructure Layer                                  │   │
│  │  ┌───────────┐ ┌──────────┐ ┌─────────────────────┐ │   │
│  │  │ Database   │ │ LangGraph│ │ Tools               │ │   │
│  │  │ Models     │ │ State    │ │ GitHub Ingestion    │ │   │
│  │  │ Repos      │ │ Nodes    │ │ CV Parser           │ │   │
│  │  └─────┬──────┘ │ Builder  │ └─────────────────────┘ │   │
│  │        │        └──────────┘                          │   │
│  │  ┌─────▼──────┐ ┌──────────┐ ┌─────────────────────┐ │   │
│  │  │ PostgreSQL │ │ LLM      │ │ Celery Workers      │ │   │
│  │  │            │ │ (OpenAI) │ │ + Redis Broker      │ │   │
│  │  └────────────┘ └──────────┘ └─────────────────────┘ │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

---

## Quick Start

### 1. Prerequisites

- Docker & Docker Compose
- An OpenAI API key

### 2. Configure Environment

Create `.env` files for the backend and the root directory.

**Root `.env` (`talent_copilot/.env`)**
```env
OPENAI_API_KEY=your_openai_api_key_here
GITHUB_TOKEN=  # Leave blank for public repos, or add a token for private repos
```

**Backend `.env` (`talent_copilot/backend/.env`)**
```env
OPENAI_API_KEY=your_openai_api_key_here
JWT_SECRET_KEY=generate_a_secure_random_string
GITHUB_TOKEN=  # Leave blank for public repos
```

### 3. Start the Platform

The entire stack (Frontend, API, Background Workers, Redis, Postgres) is containerized.

```bash
docker compose up -d --build
```

### 4. Seed the Database

To use the system, you need a tenant and a user account. Run the seed script inside the API container:

```bash
docker compose exec api python seed.py
```

This will create a default test account:
- **Tenant:** `acme-corp`
- **Email:** `recruiter@acme.com`
- **Password:** `password123`

### 5. Access the Platform

- **Frontend UI:** Open your browser to [http://localhost:8501](http://localhost:8501)
- **API Swagger Docs:** [http://localhost:8000/docs](http://localhost:8000/docs)
- **Flower (Celery Monitor):** [http://localhost:5555](http://localhost:5555)

---

## Security Guarantees

| Threat | Mitigation |
|---|---|
| Cross-tenant data access | Every DB query filters by `tenant_id` — enforced by repository interface contracts |
| Confirmation replay/spoofing | SHA-256 hash of `(tenant_id, user_id, session_id, tool_name, payload)` — recomputed and verified on execution |
| Unauthorized tool execution | Tool execution requires `APPROVED` confirmation record; denied confirmations block execution permanently |
| Token forgery | JWT with HS256 signing, tenant_id embedded in token payload |
| File injection | Upload validation: extension whitelist + size limit |
| API abuse | SlowAPI rate limiting per endpoint |

---

## Key Design Decisions

1. **Clean Architecture**: Domain layer has zero dependencies on infrastructure. All DB access goes through abstract repository interfaces.
2. **LangGraph State Machine**: Explicit states prevent accidental tool execution. The graph terminates at `confirmation_pending` — tool execution only happens via a separate API call after approval.
3. **Confirmation Integrity**: Cryptographic hash ties the confirmation to the exact (tenant, user, session, tool, payload) tuple. Any change invalidates the confirmation.
4. **Hybrid Memory**: Recent messages + session summaries + workspace artifacts (including pending CV parses) are combined for each LLM call, ensuring deep context-aware responses without unbounded token usage.
5. **Background Jobs (Celery)**: Long-running operations (GitHub ingestion, CV parsing) run in isolated Celery workers with dedicated engine factories to prevent event loop blocking.

---

## API Endpoints

| Method | Path | Description |
|---|---|---|
| POST | `/auth/login` | Authenticate and get JWT |
| POST | `/auth/refresh` | Refresh access token |
| POST | `/chat/message` | Send message, get AI response |
| GET | `/chat/sessions` | List user's sessions |
| GET | `/jobs/{id}/status` | Poll background job status |
| GET | `/workspace/candidates` | List parsed candidates |
| GET | `/workspace/repositories` | List ingested repos |
| POST | `/upload/cv` | Upload CV file |
| POST | `/ingest/github` | Request repo ingestion |
| POST | `/confirm` | Approve/deny tool action |
| GET | `/health` | Check API health |

---

## License

Proprietary — All rights reserved.

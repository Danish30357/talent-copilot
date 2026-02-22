# 🧠 TalentCopilot

A multi-tenant AI recruiting assistant built for the technical assessment. It lets recruiters chat with an AI to analyse GitHub repositories, parse CVs, and ask questions about candidates — with a Human-in-the-Loop confirmation step before anything sensitive runs.

---

## What I Built

The system has three main capabilities:

**1. GitHub Repository Analysis**
You can paste a GitHub URL into the chat and the AI will fetch the repo's file structure, languages, and README, then answer questions about what the codebase is doing.

**2. CV Parsing**
Upload a PDF or DOCX resume. The system extracts the candidate's name, email, skills, experience, and education into structured data that the AI can reason over.

**3. Contextual Chat**
After ingesting repos and CVs, you can ask the AI things like *"Is this candidate a good fit for a backend role?"* and it will answer using the actual workspace data, not generic responses.

---

## Architecture

```
Streamlit Frontend
      │  HTTP + JWT
FastAPI Backend
  ├── LangGraph Agent (state machine)
  ├── PostgreSQL (row-level tenant isolation)
  ├── Celery + Redis (background jobs)
  └── Tools: GitHub Ingestion · CV Parser
```

The LangGraph agent works as a simple state machine:

```
User message
  → conversation_node
  → tool_decision_node   (did the AI request a tool?)
  → confirmation_pending (yes → wait for human approval)
  → tool_execution       (approved → run Celery task)
  → response_generation
```

This means the AI cannot trigger any tool on its own. A human always confirms first.

---

## Multi-Tenancy

Every database table has a `tenant_id` column. Every query filters by it. Tenant A's candidates, repositories, and sessions are never accessible to Tenant B — enforced at the repository layer.

---

## Getting Started

**Prerequisites:** Docker, Docker Compose, an OpenAI API key.

**Step 1 — Set up your `.env` files**

`talent_copilot/.env`
```env
OPENAI_API_KEY=your_key_here
GITHUB_TOKEN=        # optional, leave blank for public repos
```

`talent_copilot/backend/.env`
```env
OPENAI_API_KEY=your_key_here
JWT_SECRET_KEY=any_random_string
GITHUB_TOKEN= for private repos
```

**Step 2 — Start the stack**
```bash
docker compose up -d --build
```

**Step 3 — Seed the database**
```bash
docker compose exec api python seed.py
```

This creates two tenants for testing isolation:

| Tenant | Email | Password |
|---|---|---|
| acme-corp | `recruiter@acme.com` | `password123` |
| other-corp | `other@techcorp.com` | `password123` |

**Step 4 — Open the app**

- Frontend: http://localhost:8501
- API Docs: http://localhost:8000/docs
- Celery Monitor: http://localhost:5555

---

## API Endpoints

| Method | Path | Description |
|---|---|---|
| POST | `/auth/login` | Login, returns JWT |
| POST | `/auth/refresh` | Refresh token |
| POST | `/chat` | Send message, get AI response |
| GET | `/chat/sessions` | List sessions |
| GET | `/jobs/{id}/status` | Poll background job |
| GET | `/workspace/candidates` | List saved candidates |
| GET | `/workspace/repositories` | List ingested repos |
| POST | `/upload/cv` | Upload CV file |
| POST | `/ingest/github` | Request repo ingestion |
| POST | `/confirm` | Approve or deny a tool action |
| GET | `/health` | Health check |

---

## Design Notes

- **Why LangGraph?** A plain LLM call doesn't give you control over when tools run. Using a state machine means tool execution is deterministic — it only happens after explicit human approval, every time.
- **Why Celery?** GitHub fetching and CV parsing can take 10–30 seconds. Running them as background workers means the chat API stays responsive.
- **Confirmation hashing:** Each confirmation is tied to a SHA-256 hash of the exact request (tenant, user, session, tool, payload). If anything changes, the confirmation is invalid. This prevents replay attacks.
- **Memory:** Each LLM call gets recent messages + a session summary + the full workspace snapshot (candidates, repos, active jobs). This keeps responses grounded in real data.

---

*Submitted as part of the technical assessment.*

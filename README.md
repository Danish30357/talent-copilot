# 🧠 TalentCopilot

> An enterprise-grade, multi-tenant AI recruiting assistant — built from scratch with FastAPI, LangGraph, PostgreSQL, Celery, and Streamlit.

I built this because I wanted to see what a *real* AI-powered recruiting tool looks like under the hood — not a demo wrapper over GPT that pretends to do things, but something where every feature actually works: the agent reasons through tool calls, humans stay in control of critical actions, background jobs run properly, and different companies can use the same platform without ever seeing each other's data.

Here's what actually went into it.

---

## What It Does

At its core, TalentCopilot is a chat interface where a recruiter can:

- **Drop in a GitHub repo URL** and have the AI analyse the codebase — languages used, project structure, what the code is actually doing — then answer questions about it
- **Upload a CV** and get a structured breakdown of the candidate's skills, experience, and education
- **Ask questions** like *"Is this candidate a good fit for a senior backend role?"* and get context-aware, data-driven answers — not generic ones

The important part is that none of this happens automatically. Every critical action goes through a **Human-in-the-Loop (HITL) confirmation** — a secure popup that the recruiter must explicitly approve before anything runs in the background. The AI proposes; the human decides.

---

## The Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Streamlit Frontend                        │
│   Chat UI · Confirmation Popups · CV Upload · Job Polling   │
└──────────────────────────┬──────────────────────────────────┘
                           │ HTTP / JWT
┌──────────────────────────▼──────────────────────────────────┐
│                      FastAPI Backend                         │
│                                                              │
│  Presentation   →  Auth · Chat · Confirmations              │
│  Application    →  ChatService · MemoryService               │
│  Domain         →  Entities · Interfaces · Enums            │
│  Infrastructure →  LangGraph · DB Repos · Celery · Tools    │
└──────────┬───────────────────────────────────────────────────┘
           │
    ┌──────▼──────┐   ┌─────────────┐   ┌────────────────────┐
    │  PostgreSQL  │   │ Redis Broker│   │  Celery Workers    │
    │  (row-level  │   │             │   │  GitHub Ingestion  │
    │  tenancy)    │   │             │   │  CV Parsing        │
    └──────────────┘   └─────────────┘   └────────────────────┘
```

The LangGraph state machine is what makes the agent behaviour reliable. It doesn't just fire off tool calls based on what the model decides to say — it has explicit states: `conversation → tool_decision → confirmation_pending → (user approves) → tool_execution → response`. The graph literally stops and waits for a human.

---

## Getting Started

### What You'll Need

- Docker & Docker Compose
- An OpenAI API key (or any OpenAI-compatible endpoint)

### Setup

**1. Configure your environment**

Create two `.env` files:

`talent_copilot/.env`
```env
OPENAI_API_KEY=your_key_here
GITHUB_TOKEN=        # Optional — leave blank for public repos
```

`talent_copilot/backend/.env`
```env
OPENAI_API_KEY=your_key_here
JWT_SECRET_KEY=any_long_random_string
GITHUB_TOKEN=        # Optional
```

**2. Spin everything up**

```bash
docker compose up -d --build
```

This starts the frontend, API, Celery workers, Redis, and Postgres. Everything is containerised — no local installs needed.

**3. Create a test account**

```bash
docker compose exec api python seed.py
```

This seeds two tenants so you can test multi-tenant isolation:

| Tenant | Email | Password |
|---|---|---|
| acme-corp | `recruiter@acme.com` | `password123` |
| other-corp | `other@techcorp.com` | `password123` |

**4. Open the app**

| Service | URL |
|---|---|
| Frontend | http://localhost:8501 |
| API Docs | http://localhost:8000/docs |
| Celery Monitor | http://localhost:5555 |

---

## The HITL Flow

This was probably the trickiest bit to get right. Here's how it works end-to-end:

1. User says "analyse this repo: `https://github.com/...`"
2. LangGraph agent detects a tool call and emits a `[TOOL_REQUEST]` tag
3. The backend intercepts it, creates a `Confirmation` record with a **SHA-256 hash** of the full request (tenant, user, session, tool, payload)
4. Frontend shows a dialog — *"Do you want me to ingest this repository?"*
5. User clicks Yes → the backend verifies the hash and dispatches a Celery task
6. Job runs in the background; frontend polls for completion
7. When done, the AI's next response has the full repo data in its context

If the user clicks No, the confirmation is marked `DENIED` permanently. The AI can't retry it.

---

## Security

| Concern | How It's Handled |
|---|---|
| Cross-tenant data leakage | Every single DB query filters by `tenant_id`. It's enforced at the repository layer, not ad-hoc in routes. |
| Confirmation replay attacks | Cryptographic hash ties the approval to the exact payload. Changing anything — even one character of the URL — invalidates it. |
| Unauthorised tool execution | Tools only run if a matching `APPROVED` confirmation exists in the database. No approval, no execution. |
| Token forgery | JWT signed with HS256; `tenant_id` embedded in the payload and verified on every request. |
| Bad file uploads | Whitelist of extensions (PDF, DOCX) + size cap before anything is processed. |

---

## API Reference

| Method | Endpoint | What it does |
|---|---|---|
| POST | `/auth/login` | Login and get a JWT |
| POST | `/auth/refresh` | Refresh an expired token |
| POST | `/chat` | Send a message, get an AI response |
| GET | `/chat/sessions` | List your conversation sessions |
| GET | `/jobs/{id}/status` | Check if a background job is done |
| GET | `/workspace/candidates` | List saved candidate profiles |
| GET | `/workspace/repositories` | List ingested repositories |
| POST | `/upload/cv` | Upload a CV file |
| POST | `/ingest/github` | Request a repo to be ingested |
| POST | `/confirm` | Approve or deny a pending tool action |
| GET | `/health` | API health check |

---

## Why These Tech Choices

- **FastAPI** — async-first, great for an event-driven system where most operations are I/O bound
- **LangGraph** — gives the agent a proper state machine instead of hoping the LLM decides to do the right thing every time
- **Celery + Redis** — GitHub ingestion and CV parsing can take 10-30 seconds. Running them in background workers means the chat API stays fast
- **PostgreSQL** — relational data with strong consistency is the right call for multi-tenant systems where isolation matters
- **Streamlit** — fast to build, good enough for an internal recruiting tool UI

---

*Built as a full-stack agentic AI system demonstrating HITL workflows, multi-tenancy, and LangGraph-based agent architecture.*

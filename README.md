# AgentX — Autonomous Code Review Pipeline

> **LangGraph-orchestrated 9-agent pipeline for bug detection and automated PR generation**
> Team: TriggeredAGIs | Agentic AI Hackathon 2026 | ASTRA Lab, IIT Madras
> Total Deployment Cost: **Rs. 0 / month**

---

## Architecture Overview

```
Researcher → Next.js Dashboard → GitHub URL
                                      ↓
                          Agent 1 — Orchestrator
                          (validate, clone, manifest)
                                      ↓
                          Agent 2 — Repo Intelligence
                          (AST, dependency graph, context)
                                      ↓
                    ┌─────────────────────────────┐
                    ↓                             ↓
          Agent 3 — Code Analysis      Agent 4 — Security Scanner
          (8 ML patterns, AST)         (OWASP Top 10, secrets)
                    └──────────────┬──────────────┘
                                   ↓
                          Aggregate & Rank
                          (Composite Score)
                                   ↓
                          Agent 5 — RCA
                          (Origin→Propagation→Impact)
                                   ↓
                          Agent 6 — Fix Generator
                          (Context-aware patches)
                                   ↓
                          Agent 7 — Validation
                          (Adversarial debate, 5 dimensions)
                                   ↓
                          Agent 8 — Verification
                          (Docker execution, test generation)
                                   ↓
                          Agent 9 — PR Creator
                          (Conventional Commits, academic PR)
                                   ↓
                     GitHub Pull Request (Draft)
                     + PDF Report + Supabase Audit Trail
                                   ↓
                     Adaptive Feedback Engine
                     (PR outcome → weight updates)
```

---

## Prerequisites

- Python 3.11+
- Node.js 20+
- Docker (for test verification)
- Git

## Free Accounts Required

| Service    | Purpose                        | Sign Up                          |
|------------|--------------------------------|----------------------------------|
| Groq       | LLM inference (14,400 req/day) | https://console.groq.com         |
| Supabase   | PostgreSQL + storage (500MB)   | https://supabase.com             |
| GitHub     | Repository access + PRs        | https://github.com               |
| Vercel     | Frontend hosting               | https://vercel.com (optional)    |
| Render     | Backend hosting                | https://render.com (optional)    |

---

## Quick Start

### 1. Clone and configure

```bash
git clone https://github.com/your-org/agentx.git
cd agentx
cp .env.example .env
# Edit .env with your actual keys
```

### 2. Set up Supabase

1. Create a new Supabase project at https://supabase.com
2. Go to Project Settings → Database → Connection string
3. Copy the connection string into `DATABASE_URL` in `.env`
4. Copy your project URL into `SUPABASE_URL`
5. Copy the service role key into `SUPABASE_SERVICE_ROLE_KEY`

### 3. Get a Groq API key

1. Sign up at https://console.groq.com
2. Create an API key
3. Add to `GROQ_API_KEY` in `.env`

### 4. Run with Docker (recommended)

```bash
docker compose up --build
```

- Frontend: http://localhost:3000
- Backend API: http://localhost:8000
- API Docs: http://localhost:8000/docs

### 5. Or run locally (development)

```bash
# One command setup + start
./scripts/setup.sh dev
```

This will:
- Create Python venv and install all dependencies
- Run Alembic database migrations
- Install Node.js frontend dependencies
- Start backend (port 8000) and frontend (port 3000)

---

## Environment Variables

All required variables with descriptions:

### Application
| Variable | Description | Example |
|----------|-------------|---------|
| `APP_ENV` | Environment | `production` |
| `APP_SECRET_KEY` | 64-char random secret | `openssl rand -hex 32` |
| `APP_HOST` | Bind host | `0.0.0.0` |
| `APP_PORT` | API port | `8000` |
| `APP_CORS_ORIGINS` | Allowed origins (comma-sep) | `http://localhost:3000` |

### Groq (LLM)
| Variable | Description |
|----------|-------------|
| `GROQ_API_KEY` | Your Groq API key |
| `GROQ_MODEL` | Model name (default: `llama-3.3-70b-versatile`) |

### Supabase / Database
| Variable | Description |
|----------|-------------|
| `SUPABASE_URL` | Project URL (https://xxx.supabase.co) |
| `SUPABASE_ANON_KEY` | Anon/public key |
| `SUPABASE_SERVICE_ROLE_KEY` | Service role key (server-side only) |
| `DATABASE_URL` | PostgreSQL connection string |

### GitHub
| Variable | Description |
|----------|-------------|
| `GITHUB_DEFAULT_TOKEN` | Optional default PAT for public repos |

### Docker
| Variable | Description |
|----------|-------------|
| `DOCKER_BASE_IMAGE` | Base image for verification (default: `python:3.11-slim`) |
| `DOCKER_TIMEOUT` | Container timeout in seconds (default: `300`) |
| `DOCKER_MEMORY_LIMIT` | Memory limit (default: `512m`) |

### Frontend (Next.js)
| Variable | Description |
|----------|-------------|
| `NEXT_PUBLIC_API_URL` | Backend API URL |
| `NEXT_PUBLIC_WS_URL` | Backend WebSocket URL |

---

## Build Commands

### Backend

```bash
cd backend

# Install dependencies
pip install -r requirements.txt

# Run database migrations
alembic upgrade head

# Start production server
uvicorn app:app --host 0.0.0.0 --port 8000 --workers 1

# Run tests
pytest tests/ -v

# Run tests with coverage
pytest tests/ --cov=. --cov-report=html
```

### Frontend

```bash
cd frontend

# Install dependencies
npm install

# Development server
npm run dev

# Production build
npm run build

# Start production server
npm start

# Type check
npm run type-check
```

---

## Database Migrations

```bash
cd backend

# Apply all pending migrations
alembic upgrade head

# Create a new migration
alembic revision --autogenerate -m "description"

# Rollback one migration
alembic downgrade -1

# Check current version
alembic current
```

---

## API Documentation

Full interactive docs available at: `http://localhost:8000/docs`

### Key Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/runs` | Start a new pipeline run |
| `GET` | `/api/v1/runs` | List all runs |
| `GET` | `/api/v1/runs/{id}` | Get run details + issues + patches |
| `GET` | `/api/v1/runs/{id}/report` | Download PDF report |
| `DELETE` | `/api/v1/runs/{id}` | Cancel a run |
| `WS` | `/ws/runs/{id}` | Real-time progress stream |
| `POST` | `/api/v1/feedback` | Submit PR outcome for AFE |
| `GET` | `/api/v1/afe/stats` | Adaptive Feedback Engine stats |
| `GET` | `/api/v1/health` | System health check |

### Start Run Example

```bash
curl -X POST http://localhost:8000/api/v1/runs \
  -H "Content-Type: application/json" \
  -d '{
    "repo_url": "https://github.com/owner/repo",
    "github_token": "ghp_your_token",
    "branch": "main"
  }'
```

Response:
```json
{
  "run_id": "22f07458",
  "status": "PENDING",
  "message": "Pipeline started. Connect to WebSocket for real-time updates.",
  "websocket_url": "ws://localhost:8000/ws/runs/22f07458"
}
```

### WebSocket Events

Connect to `ws://localhost:8000/ws/runs/{run_id}` to receive:

```json
// Progress event
{"type": "progress", "run_id": "22f07458", "agent": "RCA", "phase": 5, "message": "Running RCA on 3 issues..."}

// Complete event
{"type": "complete", "run_id": "22f07458", "status": "PR_CREATED", "pr_url": "https://github.com/...", "pr_number": 1}

// Error event
{"type": "error", "run_id": "22f07458", "error": "Clone failed: repository not found"}
```

### Feedback Webhook

When a PR is merged/modified/closed, call:

```bash
curl -X POST http://localhost:8000/api/v1/feedback \
  -H "Content-Type: application/json" \
  -d '{
    "run_id": "22f07458",
    "pr_number": 1,
    "outcome": "MERGED",
    "ml_patterns": ["missing_random_seed"]
  }'
```

---

## Production Deployment

### Render (Backend — Free Tier)

1. Connect your GitHub repo to Render
2. New Web Service → select `backend/` directory
3. Build Command: `pip install -r requirements.txt && alembic upgrade head`
4. Start Command: `uvicorn app:app --host 0.0.0.0 --port $PORT --workers 1`
5. Add all environment variables from `.env`

### Vercel (Frontend — Free Tier)

1. Import project from GitHub
2. Root directory: `frontend`
3. Framework: Next.js
4. Add environment variables:
   - `NEXT_PUBLIC_API_URL` = your Render backend URL
   - `NEXT_PUBLIC_WS_URL` = `wss://` + your Render backend URL

### GitHub Actions CI/CD

```yaml
# .github/workflows/deploy.yml
name: Deploy AgentX
on:
  push:
    branches: [main]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.11' }
      - run: pip install -r backend/requirements.txt
      - run: cd backend && pytest tests/ -v
  deploy-backend:
    needs: test
    runs-on: ubuntu-latest
    steps:
      - uses: renderinc/github-action@v1
        with:
          deploy-hook: ${{ secrets.RENDER_DEPLOY_HOOK }}
```

---

## Testing Instructions

```bash
# Run all tests
cd backend && pytest tests/ -v

# Run specific test module
pytest tests/test_code_analysis.py -v

# Run with coverage report
pytest tests/ --cov=. --cov-report=html
open htmlcov/index.html

# Run only fast unit tests (skip integration)
pytest tests/ -v -m "not integration"
```

---

## Production Checklist

- [ ] `.env` file has all required variables (no defaults from `.env.example`)
- [ ] `APP_SECRET_KEY` is a real 64-char random secret (`openssl rand -hex 32`)
- [ ] `GROQ_API_KEY` is valid and has available quota
- [ ] `DATABASE_URL` points to live Supabase PostgreSQL
- [ ] `alembic upgrade head` run successfully
- [ ] Docker daemon accessible for test verification (`/var/run/docker.sock`)
- [ ] `APP_CORS_ORIGINS` set to actual frontend domain (not `localhost`)
- [ ] Backend health check passing: `GET /api/v1/health`
- [ ] WebSocket connectivity tested from frontend
- [ ] GitHub webhook configured to POST to `/api/v1/feedback` on PR events
- [ ] PDF report generation tested (ReportLab installed)
- [ ] Rate limit monitoring on Groq API (14,400 req/day free tier)

---

## Project Structure

```
agentx/
├── .env.example                    # Environment variable template
├── docker-compose.yml              # Full stack Docker orchestration
├── scripts/
│   └── setup.sh                    # One-command setup script
├── migrations/
│   ├── env.py                      # Alembic environment
│   ├── 001_initial.py              # Initial schema migration
│   └── versions/                   # Future migration files
├── backend/
│   ├── main.py                     # Uvicorn entry point
│   ├── app.py                      # FastAPI application factory
│   ├── Dockerfile                  # Backend multi-stage Docker build
│   ├── requirements.txt            # Python dependencies
│   ├── alembic.ini                 # Alembic configuration
│   ├── pytest.ini                  # Test configuration
│   ├── config/
│   │   └── settings.py             # Pydantic Settings (all env vars)
│   ├── core/
│   │   ├── base_agent.py           # Abstract agent base class
│   │   ├── groq_client.py          # Groq LLM client with retry
│   │   ├── logging.py              # Structured logging (structlog)
│   │   ├── pipeline.py             # LangGraph StateGraph orchestration
│   │   └── state.py                # AgentXState TypedDict
│   ├── db/
│   │   ├── database.py             # SQLAlchemy async engine + sessions
│   │   ├── models.py               # All ORM models
│   │   └── repositories.py         # CRUD repository layer
│   ├── agents/
│   │   ├── orchestrator/           # Agent 1 — ingestion + ranking
│   │   ├── repo_intelligence/      # Agent 2 — dependency graph
│   │   ├── code_analysis/          # Agent 3 — 8 ML bug patterns
│   │   ├── security_scanner/       # Agent 4 — OWASP + secrets
│   │   ├── rca/                    # Agent 5 — root cause analysis
│   │   ├── fix_generator/          # Agent 6 — patch generation
│   │   ├── validation/             # Agent 7 — adversarial debate
│   │   ├── verification/           # Agent 8 — Docker execution
│   │   ├── pr_creator/             # Agent 9 — GitHub PR + PDF
│   │   └── adaptive_feedback/      # AFE — continuous learning
│   ├── api/
│   │   ├── routes/
│   │   │   ├── runs.py             # Pipeline run endpoints
│   │   │   └── misc.py             # WebSocket, feedback, health, AFE
│   │   └── schemas/
│   │       └── schemas.py          # Pydantic request/response models
│   ├── services/
│   │   ├── github/
│   │   │   └── github_service.py   # GitHub API + Git operations
│   │   ├── docker/
│   │   │   └── docker_service.py   # Docker test execution
│   │   └── websocket/
│   │       └── ws_manager.py       # WebSocket connection manager
│   └── tests/
│       ├── conftest.py             # Shared fixtures
│       ├── test_api.py             # API integration tests
│       ├── test_code_analysis.py   # Agent 3 unit tests
│       ├── test_orchestrator.py    # Agent 1 unit tests
│       ├── test_security_scanner.py# Agent 4 unit tests
│       └── test_groq_client.py     # Groq client unit tests
└── frontend/
    ├── Dockerfile                  # Frontend multi-stage Docker build
    ├── next.config.js              # Next.js configuration
    ├── tailwind.config.js          # Tailwind CSS configuration
    ├── package.json                # Node.js dependencies
    └── src/
        ├── app/
        │   ├── layout.tsx          # Root layout + providers
        │   ├── page.tsx            # Dashboard (start run + recent runs)
        │   ├── providers.tsx       # React Query provider
        │   ├── globals.css         # Tailwind base styles
        │   ├── runs/
        │   │   ├── page.tsx        # All runs list
        │   │   └── [runId]/
        │   │       └── page.tsx    # Run detail (issues, patches, audit)
        │   ├── afe/
        │   │   └── page.tsx        # Adaptive Feedback Engine
        │   └── settings/
        │       └── page.tsx        # System health + config
        ├── components/
        │   ├── layout/
        │   │   └── Sidebar.tsx     # Navigation sidebar
        │   └── agents/
        │       └── PipelineProgress.tsx  # Live pipeline stepper
        ├── hooks/
        │   └── useRunWebSocket.ts  # WebSocket hook
        ├── lib/
        │   └── api.ts              # Axios API client
        ├── store/
        │   └── runStore.ts         # Zustand global state
        └── types/
            └── index.ts            # TypeScript type definitions
```

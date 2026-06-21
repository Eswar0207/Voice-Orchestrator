# Multi-Tenant Agentic Voice Orchestrator

A cloud-native, multi-tenant SaaS platform that lets companies (tenants) automatically
call their leads using an AI voice agent (Vapi.ai), qualify them through a stateful
LangGraph orchestration layer, and track results on a live dashboard.

---

## 1. Architecture Overview

```
┌─────────────┐      ┌──────────────────────┐      ┌──────────────┐
│   React     │◄────►│   FastAPI Backend     │◄────►│  PostgreSQL  │
│  Dashboard  │ poll │  (single container)   │      │ (Cloud SQL)  │
└─────────────┘      │  ┌────────────────┐  │      └──────────────┘
                      │  │  LangGraph     │  │
                      │  │  Orchestrator  │  │
                      │  └───────┬────────┘  │
                      └──────────┼───────────┘
                                 │
                        ┌────────▼────────┐
                        │   Vapi.ai API    │
                        │ (outbound calls) │
                        └────────┬────────┘
                                 │ webhook (end-of-call-report)
                        ┌────────▼────────┐
                        │ POST /api/webhooks/vapi │
                        └─────────────────┘
```

The frontend and backend are bundled into **one Cloud Run service**: Vite builds the
React app into static files, which are copied into the FastAPI container and served
directly — simpler IAM, one URL, one deploy.

### LangGraph: Nodes, Edges, State

| Node | Trigger | Responsibility |
|---|---|---|
| **Router** | Every graph invocation | Inspects the input state and decides whether this is a *dispatch* request (campaign trigger from the UI) or an *evaluation* request (webhook from Vapi). |
| **Dispatch** | `company_id` present in state | Fetches all `PENDING` customers for the company, calls Vapi to place each outbound call with a dynamically built system prompt, updates status to `CALL_INITIATED` (or `FAILED` on error). |
| **Evaluate** | `transcript` present in state | Sends the transcript + company qualification criteria to an LLM (OpenAI or Gemini), which returns a structured `{status, reasoning, summary}` classification. |
| **State Update** | After Evaluate | Writes the new status to the `Customer` row and creates a `CallLog` row with transcript, summary, and metadata. |

**State** (`OrchestratorState`, a `TypedDict`) flows through the graph as a single dict:
`company_id`, `customer_id`, `vapi_call_id`, `transcript`, `summary`, `call_metadata`,
`evaluation_result`, `dispatched_count`, `errors`.

A single entry point (`router`) handles both the dispatch and evaluation flows via a
conditional edge, rather than two separate graphs — this keeps the orchestration logic
centrally testable (see `backend/tests/test_orchestrator.py`).

**Human-in-the-loop:** the evaluation prompt explicitly instructs the LLM to return
`NEEDS_REVIEW` instead of guessing whenever the transcript is ambiguous or incomplete.
This is a real, reachable outcome (covered by tests), not just an unused schema value.

---

## 2. Project Structure

```
voice_orchestrator/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI server & endpoints
│   │   ├── config.py            # Settings from environment variables
│   │   ├── database.py          # SQLAlchemy models, engine, seeding
│   │   ├── orchestrator.py      # LangGraph state machine
│   │   ├── vapi_client.py       # Vapi.ai outbound call wrapper
│   │   ├── webhook_security.py  # HMAC signature verification
│   │   └── llm_eval.py          # OpenAI/Gemini evaluation interface
│   ├── tests/                   # pytest suite (19 tests)
│   ├── requirements.txt
│   └── .env.example
├── frontend/
│   └── src/
│       ├── App.jsx              # Layout, polling, state
│       └── components/          # TenantSelector, Dashboard, LeadTable, LogViewer
├── Dockerfile                   # Multi-stage: builds frontend, bundles into backend image
├── docker-compose.yml           # Local: backend + Postgres, one command
├── cloudbuild.yaml              # GCP Cloud Build pipeline
└── deploy.sh                    # Cloud Run deployment script
```

---

## 3. Environment Variables

Copy `backend/.env.example` to `backend/.env` and fill in:

| Variable | Required | Notes |
|---|---|---|
| `DATABASE_URL` | Yes | Defaults to the local `docker-compose` Postgres connection string. |
| `VAPI_PRIVATE_KEY` | Yes (for real calls) | From your Vapi.ai dashboard. |
| `VAPI_ASSISTANT_ID` | Yes (for real calls) | The Vapi Assistant to use for outbound calls. |
| `VAPI_PHONE_NUMBER_ID` | Yes (for real calls) | The Vapi phone number to call from. |
| `VAPI_WEBHOOK_SECRET` | Yes | Shared secret configured in the Vapi dashboard for webhook signing. Used to verify `x-vapi-signature`. |
| `OPENAI_API_KEY` | One of these two | Used for transcript evaluation if set. |
| `GEMINI_API_KEY` | One of these two | Used if `OPENAI_API_KEY` is not set. |
| `ANTHROPIC_API_KEY` | Optional | Reserved — the evaluation interface (`llm_eval.py`) is provider-agnostic, so Anthropic support can be added the same way as OpenAI/Gemini. |

**Never commit `.env` files** — `.gitignore` already excludes them.

---

## 4. Local Setup & Run

### Option A — Docker Compose (recommended, zero manual install)

```bash
cp backend/.env.example backend/.env
# edit backend/.env with your real keys

docker-compose up --build
```

This starts a `postgres:16` container and the backend (with the bundled frontend)
on `http://localhost:8000`.

### Option B — Run backend and frontend separately (faster iteration)

```bash
# 1. Start Postgres only
docker-compose up postgres -d

# 2. Backend (in backend/)
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # edit with your keys
uvicorn app.main:app --reload --port 8000

# 3. Frontend (in frontend/, separate terminal)
cd frontend
npm install
npm run dev   # served at http://localhost:5173, proxies /api to :8000
```

The backend auto-creates tables and seeds two demo tenants (Apex Properties, Elite
Rentals) with 3 mock leads each on first startup.

### Exposing the webhook locally (for real Vapi calls)

```bash
ngrok http 8000
```

Register `https://<ngrok-id>.ngrok.io/api/webhooks/vapi` as your Vapi assistant's
webhook URL (Server URL) in the Vapi dashboard, and set the same shared secret there
as `VAPI_WEBHOOK_SECRET` in your `.env`.

### Running tests

```bash
cd backend
pip install -r requirements.txt
pytest tests/ -v
```

19 tests covering: database CRUD + seeding idempotency, LangGraph routing and state
transitions (including the `NEEDS_REVIEW` abstention path), and webhook signature /
structure validation.

---

## 5. Deploying to GCP Cloud Run

### Prerequisites

```bash
gcloud auth login
gcloud config set project <YOUR_PROJECT_ID>
gcloud services enable run.googleapis.com cloudbuild.googleapis.com \
  secretmanager.googleapis.com sqladmin.googleapis.com
```

### One-time: create secrets in Secret Manager

```bash
echo -n "<your-cloud-sql-connection-string>" | gcloud secrets create DATABASE_URL --data-file=-
echo -n "<your-vapi-private-key>"            | gcloud secrets create VAPI_PRIVATE_KEY --data-file=-
echo -n "<your-vapi-assistant-id>"           | gcloud secrets create VAPI_ASSISTANT_ID --data-file=-
echo -n "<your-vapi-phone-number-id>"        | gcloud secrets create VAPI_PHONE_NUMBER_ID --data-file=-
echo -n "<your-vapi-webhook-secret>"         | gcloud secrets create VAPI_WEBHOOK_SECRET --data-file=-
echo -n "<your-openai-key>"                  | gcloud secrets create OPENAI_API_KEY --data-file=-
echo -n "<your-gemini-key>"                  | gcloud secrets create GEMINI_API_KEY --data-file=-
```

### Deploy

```bash
./deploy.sh
```

This runs `gcloud builds submit` against `cloudbuild.yaml`, which:
1. Builds the multi-stage Docker image (frontend build → bundled into the FastAPI image).
2. Pushes it to Google Container Registry.
3. Deploys to Cloud Run with `--allow-unauthenticated` (required so Vapi can reach the
   public webhook endpoint) and wires all secrets from Secret Manager into the
   container's environment.

The script prints the deployed service URL and the exact webhook URL to register with
Vapi (`<service-url>/api/webhooks/vapi`).

### Dockerfile

See `Dockerfile` at the repo root — multi-stage build:
- **Stage 1** (`node:20-alpine`): installs frontend deps, runs `vite build`, output
  lands directly in `backend/app/static`.
- **Stage 2** (`python:3.11-slim`): installs backend deps, copies the backend source
  and the built static frontend from Stage 1. Single image, single Cloud Run service.

---

## 6. API Reference

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/companies` | List all tenants |
| `GET` | `/api/companies/{company_id}/customers` | List leads for a tenant |
| `GET` | `/api/customers/{customer_id}/logs` | Call logs for a lead |
| `POST` | `/api/campaigns/{company_id}/trigger` | Run the Dispatch flow for all pending leads |
| `POST` | `/api/webhooks/vapi` | Vapi end-of-call-report webhook (signature-verified) |
| `GET` | `/api/health` | Health check |

---

## 7. Webhook Security

`POST /api/webhooks/vapi` performs two sequential checks before touching the database:

1. **Signature verification** (`webhook_security.py`): the raw request body is HMAC-SHA256
   signed with `VAPI_WEBHOOK_SECRET` and compared against the `x-vapi-signature` header
   using `hmac.compare_digest` (constant-time, prevents timing attacks). Missing or
   invalid signatures return `401` immediately — no parsing, no DB writes.
2. **Structural validation**: after the signature passes, the payload is checked for
   `type == "end-of-call-report"` and a `metadata.customer_id`. Malformed payloads
   return `400`.

Only requests that pass both checks reach the LangGraph evaluation flow.

---

## 8. Known Limitations / Notes

- The seeded mock phone numbers (`+1555...`) are placeholders — replace with real
  numbers in the database (or via a future "add lead" endpoint) before placing live
  test calls.
- `ANTHROPIC_API_KEY` is read into config but not yet wired into `llm_eval.py`; the
  interface is provider-agnostic so adding `_evaluate_with_anthropic()` follows the
  same pattern as the existing OpenAI/Gemini functions.
- Frontend polling is fixed at 5s; for a production system this would likely move to
  a websocket or server-sent-events push model.

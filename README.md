# Parking Reservation Chatbot

An AI parking-reservation system built with **LangChain** + **LangGraph** on a **Retrieval-Augmented
Generation (RAG)** architecture, with a genuine human-in-the-loop administrator approval step and a
real **MCP** server that persists confirmed reservations.

All four stages are implemented in a **single LangGraph `StateGraph`**:

1. **RAG chatbot** (Stage 1) — answers parking questions from a vector store, looks up live
   availability/pricing/hours from SQL, and interactively collects reservation details.
2. **Human-in-the-loop admin approval** (Stage 2) — once a reservation is collected, the graph
   genuinely pauses (`interrupt()`) and waits for an administrator's decision via a REST API /
   Streamlit dashboard.
3. **MCP server** (Stage 3) — a real Model Context Protocol server exposing a
   `save_confirmed_reservation` tool that writes approved reservations to a file.
4. **LangGraph orchestration** (Stage 4) — the same graph, checkpointed to SQLite, ties
   intent routing → reservation collection → admin pause/resume → MCP storage → user confirmation
   into one pipeline.

## Architecture

```
User ──► Streamlit chat UI ──► FastAPI /chat ──► LangGraph StateGraph (checkpointed, SQLite)
                                                       │
                      ┌───────────────┬────────────────┼────────────────┐
                      ▼               ▼                ▼                ▼
              classify_intent   handle_dynamic_info  handle_static_info  handle_reservation
                                  (PostgreSQL)         (Qdrant + LLM)      (slot-filling)
                                                                               │
                                                                   reservation complete?
                                                                               ▼
                                                                      submit_to_admin
                                                                (creates Reservation + AdminRequest,
                                                                 rejects overlapping double-bookings)
                                                                               ▼
                                                                    await_admin_decision
                                                              ⏸ interrupt() — graph genuinely pauses,
                                                              state checkpointed to SQLite
                                                                               │
                                        Administrator (Streamlit dashboard / REST API)
                                        POST /admin/requests/{id}/decision — resumes the
                                        paused thread with Command(resume=...)
                                                                               │
                                                   ┌───────────────────────────┴───────────────┐
                                                   ▼                                             ▼
                                            store_via_mcp                                  reject_notify
                                      (calls the MCP server's                        (reservation marked
                                       save_confirmed_reservation                      "rejected", MCP never
                                       tool; on failure, marks                         called)
                                       "approved_pending_storage"
                                       instead of crashing)
                                                   ▼
                                          guardrail_filter (PII redaction) ──► response to user

Static knowledge (location, rules, FAQs, booking process)      → Qdrant (vector DB)
Dynamic data (availability, prices, hours, reservations,
admin requests, approval status)                                 → PostgreSQL (SQL DB)
Confirmed reservations                                            → MCP server → text file + DB status
```

See [`docs/architecture.md`](docs/architecture.md) for more detail on each node.

## Technology stack

- **Backend**: Python 3.11, FastAPI, Pydantic/`pydantic-settings`
- **Orchestration**: LangGraph (`interrupt()`/`Command(resume=...)` + `SqliteSaver` checkpointer)
- **LLM/embeddings**: LangChain + `AzureChatOpenAI`/`AzureOpenAIEmbeddings` against the EPAM DIAL proxy
- **RAG**: Qdrant vector store, markdown header + recursive chunking
- **SQL**: PostgreSQL via SQLAlchemy (dynamic data, reservations, admin requests)
- **MCP**: official `mcp` Python SDK (`FastMCP`, streamable-HTTP transport)
- **Frontend**: Streamlit (user chat + a separate admin dashboard page)
- **Guardrails**: regex + spaCy NER PII detection/redaction, prompt-injection/input validation
- **Testing**: pytest (unit + integration, all external services mocked)
- **Docker**: Compose stack for Qdrant + PostgreSQL + MCP server + app
- **CI**: GitHub Actions (install deps, spaCy model, run pytest)

## Project structure

```
app/
  config.py                   Settings (env vars): DIAL, Qdrant, Postgres, MCP, checkpointer paths
  main.py                     FastAPI app (chat + admin routers), DB init on startup
  agents/
    reservation_agent.py      Slot-filling + optional LLM multi-field extraction
  api/
    routes.py                 POST /chat, GET /health, GET /reservations/{request_id}
    admin_routes.py           GET /admin/requests, POST /admin/requests/{id}/decision
    schemas.py                Pydantic request/response models
  database/
    models.py                 Reservation, AdminRequest + dynamic-data tables
    dynamic_service.py        All DB reads/writes (availability, pricing, hours,
                               reservations, admin requests, double-booking check)
  graph/
    state.py                  ChatState TypedDict
    chatbot_graph.py           The one LangGraph StateGraph covering Stages 1, 2 & 4
    checkpointer.py            SQLite-backed checkpointer (durable interrupt/resume)
  mcp/
    server.py                 MCP server: save_confirmed_reservation tool (Stage 3)
    client.py                 MCP client used by the graph's store_via_mcp node
  rag/
    ingest.py, retriever.py, chain.py   Load→guardrail→embed→Qdrant, retriever, RAG chain
  security/
    guardrails.py              PII detection/redaction + prompt-injection input guardrail
frontend/
  streamlit_app.py             User chat UI (with pending-approval status polling)
  pages/1_Admin_Dashboard.py   Administrator dashboard (approve/reject)
data/
  knowledge/                   Static markdown knowledge base
  reservations/                MCP server output (confirmed_reservations.txt, gitignored)
  state/                       SQLite checkpointer DB (gitignored)
evaluation/                    Retrieval (Recall@K/Precision@K) + latency evaluation
tests/                         pytest suite (unit + integration, 70+ tests)
docker/                        docker-compose for Qdrant + PostgreSQL + MCP + app
.github/workflows/ci.yml       CI: installs deps + spaCy model, runs pytest
```

## Installation

```bash
python -m venv .venv
.venv/Scripts/activate            # Windows
# source .venv/bin/activate       # macOS/Linux
pip install -r requirements.txt
python -m spacy download en_core_web_sm
```

## Environment variables

```bash
cp .env.example .env
```

Key variables (see `.env.example` for the full list):

| Variable | Purpose |
|---|---|
| `DIAL_API_KEY`, `DIAL_ENDPOINT`, `DIAL_CHAT_DEPLOYMENT`, `DIAL_EMBEDDING_DEPLOYMENT` | LLM/embeddings (Azure OpenAI SDK via the EPAM DIAL proxy) |
| `QDRANT_HOST`/`PORT`/`COLLECTION` | Vector DB for static knowledge |
| `POSTGRES_*` | SQL DB for dynamic data, reservations, admin requests |
| `MCP_HOST`/`PORT`/`MCP_AUTH_TOKEN` | MCP server address + shared auth token |
| `CHECKPOINT_DB_PATH` | SQLite file backing the LangGraph checkpointer |
| `RESERVATIONS_FILE_PATH` | Output file for confirmed reservations |

Never commit `.env` — it's gitignored.

## Running the application

```bash
# 1. Start Qdrant + PostgreSQL
cd docker && docker compose up -d qdrant postgres && cd ..

# 2. Seed dynamic data + ingest static knowledge
python -m app.database.seed
python -m app.rag.ingest

# 3. Run the MCP server (Stage 3)
python -m app.mcp.server

# 4. Run the main API (Stage 1/2/4), in another terminal
uvicorn app.main:app --reload

# 5. Run the chat UI + admin dashboard (Streamlit), in another terminal
streamlit run frontend/streamlit_app.py
# Admin dashboard: sidebar → "Admin Dashboard" (or http://localhost:8501/Admin_Dashboard)
```

Or everything via Docker Compose (`cd docker && docker compose up -d`), which also builds and runs
the `app` and `mcp` services.

## Usage

```bash
# Ask an informational question
curl -X POST http://localhost:8000/chat -H "Content-Type: application/json" \
  -d '{"session_id":"demo","message":"What are your working hours?"}'

# Make a reservation (same session_id across turns)
curl -X POST http://localhost:8000/chat -H "Content-Type: application/json" \
  -d '{"session_id":"demo","message":"I would like to book a parking space"}'
# ... keep posting first name / surname / car number / start / end time

# Check status while pending
curl http://localhost:8000/reservations/<request_id>

# Administrator: list pending requests and decide
curl http://localhost:8000/admin/requests?status=pending
curl -X POST http://localhost:8000/admin/requests/<request_id>/decision \
  -H "Content-Type: application/json" -d '{"decision": "approved"}'
```

An approved reservation is appended to `data/reservations/confirmed_reservations.txt` as:

```
Name | Car Number | Reservation Period | Approval Time
```

## Running tests

```bash
pytest -q
```

All external services (LLM, Qdrant, PostgreSQL, the MCP server) are mocked, so the suite runs with
no API key or running containers — this is also what CI runs on every push/PR.

## Running evaluation

```bash
python -m evaluation.evaluate_retrieval
python -m evaluation.evaluate_latency
```

Requires a reachable DIAL endpoint and a populated Qdrant collection (see **Known limitations**).

## Admin dashboard (Stage 2)

`frontend/pages/1_Admin_Dashboard.py` lists pending/approved/rejected requests with
Approve/Reject buttons, calling `app/api/admin_routes.py`. Approving/rejecting resumes the paused
LangGraph thread for that user's chat session via `Command(resume=...)`, so the backend state and
the chatbot's eventual response to the user stay in sync with the admin's decision.

## LangGraph workflow (Stage 4)

`app/graph/chatbot_graph.py` is one `StateGraph`, compiled with a `SqliteSaver` checkpointer keyed
by `thread_id = session_id`:

```
classify_intent → {reservation | dynamic_info | static_info | awaiting_admin}
handle_reservation → submit_to_admin (double-booking check) → await_admin_decision ⏸interrupt()
  → {store_via_mcp | reject_notify} → guardrail_filter → END
```

Because the checkpointer persists state to disk, a reservation genuinely paused at
`await_admin_decision` survives separate HTTP requests — and an app restart — until an
administrator decides. `app/api/admin_routes.py` resumes the exact paused thread with
`Command(resume={"decision": ...})`.

## Guardrails

`app/security/guardrails.py`:

- **Ingestion-time**: documents are scanned before embedding; anything that looks like PII is
  rejected and never stored in Qdrant (`is_safe_for_vector_store`).
- **Response-time**: every chatbot response is scanned and PII is redacted before reaching the
  user (`redact_pii`, regex + spaCy NER).
- **Input guardrail**: every incoming chat message is validated before it reaches the graph
  (`validate_user_message`) — rejects empty/oversized input and anything matching prompt-injection
  / internal-detail-probing patterns (e.g. "ignore previous instructions", "reveal your system
  prompt", SQL-injection-shaped strings), without ever reaching the LLM or DB.
- Reservation fields (name, car number, dates) are validated by strict regex/parsers before
  touching the database; all DB access goes through parameterized SQLAlchemy queries.
- MCP tool inputs are independently re-validated server-side (see below) — the chatbot's
  validation is not trusted as the only line of defense.

## MCP server (Stage 3)

`app/mcp/server.py` is a real MCP server (`mcp` SDK's `FastMCP`, streamable-HTTP transport)
exposing one tool, `save_confirmed_reservation(token, request_id, name, car_number, period_start,
period_end, approval_time)`. Security:

- Shared-secret token check (`MCP_AUTH_TOKEN`) on every call.
- Strict regex validation of every field; rejects end-before-start periods.
- The output path is fixed server-side from config, never caller-supplied, and is resolved +
  checked to stay inside `data/` — ruling out path traversal / arbitrary file writes.
- Delimiter/newline characters are stripped from written fields as defense-in-depth, even though
  the validators already reject them.
- No internal error detail is leaked to the caller; failures raise a typed
  `ReservationValidationError` with a safe message.

If the MCP server is unreachable or times out, `app/graph/chatbot_graph.py`'s `store_via_mcp` node
catches `McpUnavailableError`, marks the reservation `approved_pending_storage` (never crashes,
never silently drops the approval), logs the failure, and tells the user it will be retried —
exactly the Stage 3 fallback the spec asks for (verified by killing the MCP process mid-flow during
testing).

## Edge cases handled

- Empty / oversized / prompt-injection chat input → rejected before reaching the graph.
- Invalid car number / name / date, or end-time before start-time → rejected with a clear message,
  reservation not advanced.
- Overlapping reservation for the same car number while an earlier request is still
  pending/approved → blocked with an explanation, no duplicate admin request created.
- Re-deciding an already-approved/rejected request → idempotent no-op response, not a silent
  state flip.
- Unknown `request_id` on the status or decision endpoints → `404`, not a crash.
- MCP server down/unreachable at approval time → `approved_pending_storage`, reservation file
  untouched, no exception surfaced to the user.
- Chat graph raising unexpectedly → `502` with a generic message, no stack trace leaked.
- RAG/LLM/vector-store failure → static-info node degrades to a friendly fallback message instead
  of propagating the exception.

## Evaluation results

See [`docs/architecture.md`](docs/architecture.md) and `evaluation/` for methodology. Live
Recall@K/Precision@K and latency numbers require a reachable DIAL endpoint (see **Known
limitations**) — the evaluation scripts and dataset are in place and were exercised against a
pre-populated Qdrant collection.

## Screenshots

See `screenshots/` for Stage 1 UI screenshots. The Stage 2-4 admin dashboard and approval flow were
verified via live API calls (documented in the implementation report) rather than new screenshots,
given the environment's network constraints on launching a full browser session.

## Troubleshooting

- **"MCP server unavailable" on every approval**: confirm `python -m app.mcp.server` is running and
  `MCP_PORT` in `.env` matches, and that nothing else is already bound to that port.
- **RAG answers always fall back to "can't look that up right now"**: `DIAL_API_KEY` is missing/
  invalid, or the DIAL endpoint isn't reachable from your network (corporate VPN required) — the
  chatbot degrades gracefully instead of crashing.
- **spaCy NER name-redaction doesn't seem to run**: run `python -m spacy download en_core_web_sm`;
  the guardrail falls back to regex-only PII detection without it.
- **Postgres connection errors**: confirm `docker compose up -d postgres` is running and
  `POSTGRES_PORT=5433` (not 5432) matches your `.env`.
- **A reservation seems "stuck" pending**: check `GET /admin/requests?status=pending` — if it's not
  there, the session's LangGraph thread may have been invoked with a different `session_id`; the
  chatbot's `session_id` and the paused thread's `thread_id` must match.

## Known limitations

- **DIAL/LLM connectivity**: this environment's egress to the EPAM DIAL proxy
  (`ai-proxy.lab.epam.com`) was not reachable during development/testing (requires VPN), so the
  RAG-answer and LLM-based multi-field-extraction code paths were verified via mocked unit tests
  and graceful-fallback behavior, not a live LLM call. Every other path (reservation slot-filling,
  admin approval/rejection, LangGraph interrupt/resume, MCP storage + failure fallback,
  double-booking guard) was verified against the real running Postgres/Qdrant/MCP stack.
- **Single-process session state for `/chat`**: the LangGraph checkpointer is a local SQLite file,
  which is fine for a single-instance demo but would need a shared backend (Postgres-backed
  checkpointer) to scale horizontally.
- **No email/SMS admin notification channel**: the admin learns about pending requests by viewing
  the dashboard, not a push notification — acceptable for this scope per the spec's preference for
  a web dashboard.
- **PowerPoint deck**: not regenerated as part of this pass; `docs/generate_pptx.py` exists from
  Stage 1 and would need updating to cover Stages 2-4.

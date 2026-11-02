# Architecture — Stage 1

## Goal

Provide a chatbot that can (a) answer informational questions about a parking facility and
(b) interactively collect reservation details from a user, while never leaking personal data
through the vector store or its responses.

## Data split: static vs. dynamic

| Data | Where it lives | Why |
|---|---|---|
| General info, location, booking process, reservation rules, FAQs | **Qdrant** (vector DB) | Rarely changes; good fit for semantic retrieval over unstructured text. |
| Space availability, prices, working hours | **PostgreSQL** (SQL DB) | Changes frequently/independently of the written documentation; must be looked up live rather than answered from a stale embedded chunk. |
| Reservation requests | **PostgreSQL** | Structured, transactional data that Stage 2's admin-approval workflow will read/update. |

This split also reduces the PII surface of the vector store: personal data (names, car numbers)
is never written to Qdrant, only to PostgreSQL, which isn't used for open-ended retrieval.

## LangGraph flow

```
START
  │
  ▼
classify_intent ──────────────┬─────────────────────┬───────────────────┐
  │ (keyword rules; "continue  │                     │                   │
  │  reservation" overrides    │                     │                   │
  │  everything else)          │                     │                   │
  ▼                            ▼                     ▼
handle_reservation      handle_dynamic_info    handle_static_info
  │ (slot-filling:        │ (queries             │ (Qdrant retriever
  │  name, surname,       │  PostgreSQL via      │  + ChatOpenAI,
  │  car number, start/   │  dynamic_service)     │  "answer only from
  │  end time; writes      │                      │  context")
  │  Reservation row       │                      │
  │  once complete)        │                      │
  └────────────┬───────────┴──────────┬───────────┘
               ▼                      ▼
                    guardrail_filter
                          │ (redact_pii on the final response)
                          ▼
                         END
```

Each user turn is one graph invocation. Conversation state (`reservation_slots`,
`reservation_in_progress`) is persisted per `session_id` by the FastAPI layer (`app/api/routes.py`)
and fed back in as the previous state on the next turn — this is what lets the reservation
slot-filling survive across multiple HTTP requests.

## Guardrails

`app/security/guardrails.py` implements two checks built on the same detector
(`scan_for_pii` = regex rules + optional spaCy NER):

- `is_safe_for_vector_store(text)` — used by `app/rag/ingest.py` before embedding any chunk.
  Chunks that fail are logged and skipped, never reaching Qdrant.
- `redact_pii(text)` — used by the `guardrail_filter` graph node on every outgoing response, as a
  defense-in-depth measure in case the LLM echoes something sensitive from the dynamic-data lookup
  or from user input.

## Evaluation

- **Retrieval accuracy**: `evaluation/evaluate_retrieval.py` runs a labeled set of 10 questions
  (`evaluation/eval_dataset.json`) against the retriever and computes Recall@K / Precision@K by
  checking whether the retrieved chunk's markdown-header metadata (`section`/`subsection`) matches
  the expected one.
- **Latency**: `evaluation/evaluate_latency.py` measures retrieval-only latency and full
  (retrieval + LLM generation) latency across the same question set, reporting p50/p95/max.

Numbers from the most recent run are in [`evaluation/REPORT.md`](../evaluation/REPORT.md).

## What's deliberately out of scope for Stage 1

- Human-in-the-loop admin approval (Stage 2) — reservations are stored with
  `status="pending_admin_approval"` so Stage 2 can pick them up without a schema change.
- MCP server / writing approved reservations to a file (Stage 3).
- A single LangGraph that also orchestrates the admin and MCP steps (Stage 4) — Stage 1's graph
  only covers the user-facing chatbot.

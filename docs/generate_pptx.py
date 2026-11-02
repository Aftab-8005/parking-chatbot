"""Generates docs/Stage1_Presentation.pptx explaining how the Stage 1 solution
works. Run with: python docs/generate_pptx.py
(requires `pip install python-pptx`, not a runtime dependency of the app)."""

from pathlib import Path

from pptx import Presentation
from pptx.util import Inches, Pt

OUT_PATH = Path(__file__).parent / "Stage1_Presentation.pptx"

prs = Presentation()
prs.slide_width = Inches(13.33)
prs.slide_height = Inches(7.5)

TITLE_LAYOUT = prs.slide_layouts[0]
CONTENT_LAYOUT = prs.slide_layouts[1]


def add_title_slide(title: str, subtitle: str):
    slide = prs.slides.add_slide(TITLE_LAYOUT)
    slide.shapes.title.text = title
    slide.placeholders[1].text = subtitle
    return slide


def add_bullet_slide(title: str, bullets: list[str]):
    slide = prs.slides.add_slide(CONTENT_LAYOUT)
    slide.shapes.title.text = title
    body = slide.placeholders[1].text_frame
    body.clear()
    for i, bullet in enumerate(bullets):
        p = body.paragraphs[0] if i == 0 else body.add_paragraph()
        p.text = bullet
        p.level = 0
        p.font.size = Pt(20)
    return slide


def add_code_slide(title: str, code: str):
    slide = prs.slides.add_slide(prs.slide_layouts[5])
    slide.shapes.title.text = title
    textbox = slide.shapes.add_textbox(Inches(0.5), Inches(1.4), Inches(12.3), Inches(5.6))
    tf = textbox.text_frame
    tf.word_wrap = True
    lines = code.strip().split("\n")
    for i, line in enumerate(lines):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.text = line
        p.font.name = "Consolas"
        p.font.size = Pt(14)
    return slide


add_title_slide(
    "Parking Reservation Chatbot",
    "Stage 1 — RAG Chatbot with Guardrails\nLangChain + LangGraph + Qdrant + PostgreSQL",
)

add_bullet_slide(
    "Goal",
    [
        "Build a chatbot that answers questions about a parking facility",
        "Collect reservation details interactively (name, surname, car number, period)",
        "Prevent exposure of sensitive/personal data",
        "Evaluate retrieval accuracy and latency",
    ],
)

add_bullet_slide(
    "Tech stack",
    [
        "Python, FastAPI, Streamlit",
        "LangChain + LangGraph for orchestration",
        "Qdrant — vector DB for static knowledge",
        "PostgreSQL — SQL DB for dynamic data (availability, prices, hours, reservations)",
        "spaCy (pretrained NER) + regex — PII guardrails",
        "Docker Compose / Terraform for infrastructure",
    ],
)

add_bullet_slide(
    "Why split static vs. dynamic data?",
    [
        "Static: general info, location, booking process, FAQs -> embedded in Qdrant",
        "Dynamic: availability, prices, working hours -> looked up live from PostgreSQL",
        "Avoids answering with stale prices/availability baked into old embeddings",
        "Keeps personal/transactional data out of the vector store entirely",
    ],
)

add_code_slide(
    "LangGraph flow",
    """
START
  -> classify_intent (keyword routing)
       -> handle_reservation   (slot-filling agent)
       -> handle_dynamic_info  (PostgreSQL lookup)
       -> handle_static_info   (RAG: Qdrant retriever + ChatOpenAI)
  -> guardrail_filter (redact_pii on the final response)
  -> END

Conversation state (slots, reservation_in_progress) is persisted
per session_id between HTTP requests by the FastAPI layer.
""",
)

add_bullet_slide(
    "Guardrails — two checkpoints",
    [
        "Ingestion time: every knowledge-base chunk is scanned before being embedded;",
        "  PII-containing chunks are rejected and never stored in Qdrant",
        "Response time: every chatbot reply is scanned and PII is redacted",
        "  before reaching the user",
        "Detection: regex (email, phone, credit card, SSN) + spaCy en_core_web_sm NER (PERSON)",
        "Graceful degradation to regex-only if the spaCy model isn't installed",
    ],
)

add_bullet_slide(
    "Evaluation approach",
    [
        "Recall@K / Precision@K over a 10-question labeled set",
        "  (evaluation/eval_dataset.json, evaluation/evaluate_retrieval.py)",
        "Relevance judged by matching retrieved chunk's markdown section/subsection",
        "  metadata against the expected one",
        "Latency: retrieval-only vs. full retrieval+generation, p50/p95/max",
        "  (evaluation/evaluate_latency.py)",
        "See evaluation/REPORT.md for the latest numbers",
    ],
)

add_bullet_slide(
    "Testing & CI",
    [
        "30+ pytest tests across every module, all external services mocked",
        "  (OpenAI, Qdrant, PostgreSQL) so the suite runs with no API key/containers",
        "GitHub Actions workflow runs the full suite on every push/PR",
        "Docker Compose + Terraform (docker provider) both stand up Qdrant + PostgreSQL",
    ],
)

add_bullet_slide(
    "Next stages",
    [
        "Stage 2: human-in-the-loop admin approval agent",
        "Stage 3: MCP server writes approved reservations to a file",
        "Stage 4: single LangGraph orchestrating chatbot + admin + MCP",
    ],
)

prs.save(OUT_PATH)
print(f"Saved {OUT_PATH}")

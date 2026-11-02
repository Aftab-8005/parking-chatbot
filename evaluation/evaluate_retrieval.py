"""Measures retrieval accuracy of the RAG system using Recall@K and Precision@K
against a small labeled evaluation set (evaluation/eval_dataset.json)."""

import json
from pathlib import Path

from app.rag.retriever import get_retriever

DATASET_PATH = Path(__file__).parent / "eval_dataset.json"


def load_dataset() -> list[dict]:
    return json.loads(DATASET_PATH.read_text(encoding="utf-8"))


def _is_relevant(doc, item: dict) -> bool:
    metadata = doc.metadata
    if item.get("expected_subsection"):
        return metadata.get("subsection") == item["expected_subsection"]
    return metadata.get("section") == item.get("expected_section")


def evaluate(k: int = 3) -> dict:
    dataset = load_dataset()
    retriever = get_retriever(k=k)

    precisions, recalls = [], []
    for item in dataset:
        docs = retriever.invoke(item["question"])
        relevant_hits = sum(1 for d in docs if _is_relevant(d, item))
        precisions.append(relevant_hits / max(len(docs), 1))
        recalls.append(1.0 if relevant_hits > 0 else 0.0)

    return {
        "k": k,
        "num_queries": len(dataset),
        "precision_at_k": round(sum(precisions) / len(precisions), 3),
        "recall_at_k": round(sum(recalls) / len(recalls), 3),
    }


if __name__ == "__main__":
    for k in (1, 3, 5):
        print(evaluate(k=k))

"""Measures request latency of the RAG system: retrieval-only vs. full
retrieval + LLM-generation latency, reporting p50/p95/max."""

import statistics
import time

from app.rag.chain import answer_static_question
from app.rag.retriever import get_retriever
from evaluation.evaluate_retrieval import load_dataset


def _summarize(timings: list[float]) -> dict:
    if not timings:
        return {"count": 0, "p50_seconds": None, "p95_seconds": None, "max_seconds": None}
    ordered = sorted(timings)
    p95_index = max(int(len(ordered) * 0.95) - 1, 0)
    return {
        "count": len(timings),
        "p50_seconds": round(statistics.median(ordered), 3),
        "p95_seconds": round(ordered[p95_index], 3),
        "max_seconds": round(max(ordered), 3),
    }


def measure_retrieval_latency(k: int = 3) -> dict:
    retriever = get_retriever(k=k)
    timings = []
    for item in load_dataset():
        start = time.perf_counter()
        retriever.invoke(item["question"])
        timings.append(time.perf_counter() - start)
    return _summarize(timings)


def measure_end_to_end_latency() -> dict:
    timings = []
    for item in load_dataset():
        start = time.perf_counter()
        answer_static_question(item["question"])
        timings.append(time.perf_counter() - start)
    return _summarize(timings)


if __name__ == "__main__":
    print("Retrieval-only latency:", measure_retrieval_latency())
    print("End-to-end (retrieval + LLM) latency:", measure_end_to_end_latency())

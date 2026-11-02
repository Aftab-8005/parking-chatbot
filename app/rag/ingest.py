"""Load the static knowledge documents, run them through the sensitive-data
guardrail, embed them, and upsert them into the Qdrant vector store."""

from __future__ import annotations

from pathlib import Path

from langchain_core.documents import Document
from langchain_openai import OpenAIEmbeddings
from langchain_qdrant import QdrantVectorStore
from langchain_text_splitters import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter
from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance, VectorParams

from app.config import settings
from app.security.guardrails import is_safe_for_vector_store

KNOWLEDGE_DIR = Path(__file__).resolve().parents[2] / "data" / "knowledge"

_HEADERS_TO_SPLIT_ON = [("#", "title"), ("##", "section"), ("###", "subsection")]


def load_and_split_documents() -> list[Document]:
    header_splitter = MarkdownHeaderTextSplitter(headers_to_split_on=_HEADERS_TO_SPLIT_ON)
    char_splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)

    documents: list[Document] = []
    for path in sorted(KNOWLEDGE_DIR.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        header_chunks = header_splitter.split_text(text)
        for chunk in header_chunks:
            chunk.metadata["source"] = path.name
            documents.extend(char_splitter.split_documents([chunk]))
    return documents


def filter_safe_documents(documents: list[Document]) -> tuple[list[Document], list[Document]]:
    """Split documents into (safe, rejected) based on the PII guardrail."""
    safe, rejected = [], []
    for doc in documents:
        if is_safe_for_vector_store(doc.page_content):
            safe.append(doc)
        else:
            rejected.append(doc)
    return safe, rejected


def get_qdrant_client() -> QdrantClient:
    return QdrantClient(host=settings.qdrant_host, port=settings.qdrant_port)


def ensure_collection(client: QdrantClient, vector_size: int) -> None:
    if not client.collection_exists(settings.qdrant_collection):
        client.create_collection(
            collection_name=settings.qdrant_collection,
            vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
        )


def ingest() -> int:
    """Embed and upsert all safe static-knowledge documents. Returns the
    number of chunks written."""
    documents = load_and_split_documents()
    safe_documents, rejected = filter_safe_documents(documents)

    if rejected:
        print(f"Guardrail rejected {len(rejected)} chunk(s) containing possible PII; they were not stored.")

    if not safe_documents:
        print("No safe documents to ingest.")
        return 0

    embeddings = OpenAIEmbeddings(
        model=settings.openai_embedding_model,
        api_key=settings.openai_api_key,
    )

    client = get_qdrant_client()
    probe_vector = embeddings.embed_query("probe")
    ensure_collection(client, vector_size=len(probe_vector))

    vectorstore = QdrantVectorStore(
        client=client,
        collection_name=settings.qdrant_collection,
        embedding=embeddings,
    )
    vectorstore.add_documents(safe_documents)
    return len(safe_documents)


if __name__ == "__main__":
    count = ingest()
    print(f"Ingested {count} chunk(s) into Qdrant collection '{settings.qdrant_collection}'.")

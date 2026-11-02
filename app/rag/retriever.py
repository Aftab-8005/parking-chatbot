from langchain_openai import OpenAIEmbeddings
from langchain_qdrant import QdrantVectorStore
from qdrant_client import QdrantClient

from app.config import settings


def get_vectorstore() -> QdrantVectorStore:
    client = QdrantClient(host=settings.qdrant_host, port=settings.qdrant_port)
    embeddings = OpenAIEmbeddings(
        model=settings.openai_embedding_model,
        api_key=settings.openai_api_key,
    )
    return QdrantVectorStore(
        client=client,
        collection_name=settings.qdrant_collection,
        embedding=embeddings,
    )


def get_retriever(k: int = 3):
    return get_vectorstore().as_retriever(search_kwargs={"k": k})

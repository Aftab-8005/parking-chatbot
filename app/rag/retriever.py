from langchain_openai import AzureOpenAIEmbeddings
from langchain_qdrant import QdrantVectorStore
from qdrant_client import QdrantClient

from app.config import settings


def get_embeddings() -> AzureOpenAIEmbeddings:
    return AzureOpenAIEmbeddings(
        azure_deployment=settings.dial_embedding_deployment,
        azure_endpoint=settings.dial_endpoint,
        api_version=settings.dial_api_version,
        api_key=settings.dial_api_key,
        timeout=settings.llm_request_timeout_seconds,
        max_retries=0,
    )


def get_vectorstore() -> QdrantVectorStore:
    client = QdrantClient(host=settings.qdrant_host, port=settings.qdrant_port)
    embeddings = get_embeddings()
    return QdrantVectorStore(
        client=client,
        collection_name=settings.qdrant_collection,
        embedding=embeddings,
    )


def get_retriever(k: int = 3):
    return get_vectorstore().as_retriever(search_kwargs={"k": k})

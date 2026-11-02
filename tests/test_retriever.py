from unittest.mock import MagicMock

from app.rag import retriever


def test_get_vectorstore_builds_client_and_embeddings_with_settings(monkeypatch):
    fake_client = MagicMock()
    fake_embeddings = MagicMock()
    fake_vectorstore = MagicMock()

    monkeypatch.setattr(retriever, "QdrantClient", MagicMock(return_value=fake_client))
    monkeypatch.setattr(retriever, "OpenAIEmbeddings", MagicMock(return_value=fake_embeddings))
    monkeypatch.setattr(retriever, "QdrantVectorStore", MagicMock(return_value=fake_vectorstore))

    result = retriever.get_vectorstore()

    assert result is fake_vectorstore
    retriever.QdrantVectorStore.assert_called_once_with(
        client=fake_client,
        collection_name=retriever.settings.qdrant_collection,
        embedding=fake_embeddings,
    )


def test_get_retriever_passes_k_to_search_kwargs(monkeypatch):
    fake_vectorstore = MagicMock()
    monkeypatch.setattr(retriever, "get_vectorstore", lambda: fake_vectorstore)

    retriever.get_retriever(k=5)

    fake_vectorstore.as_retriever.assert_called_once_with(search_kwargs={"k": 5})


def test_get_retriever_defaults_to_k_3(monkeypatch):
    fake_vectorstore = MagicMock()
    monkeypatch.setattr(retriever, "get_vectorstore", lambda: fake_vectorstore)

    retriever.get_retriever()

    fake_vectorstore.as_retriever.assert_called_once_with(search_kwargs={"k": 3})

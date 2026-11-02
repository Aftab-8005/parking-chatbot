from langchain_core.documents import Document

from app.rag.ingest import filter_safe_documents, load_and_split_documents


def test_load_and_split_documents_produces_chunks_with_metadata():
    docs = load_and_split_documents()
    assert len(docs) > 0
    assert all("source" in d.metadata for d in docs)


def test_filter_safe_documents_rejects_pii_chunk():
    safe_doc = Document(page_content="The parking is open from 6am to 11pm.")
    pii_doc = Document(page_content="Contact jane.doe@example.com for details.")

    safe, rejected = filter_safe_documents([safe_doc, pii_doc])

    assert safe_doc in safe
    assert pii_doc in rejected

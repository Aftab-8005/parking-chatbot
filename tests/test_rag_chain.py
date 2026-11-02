from unittest.mock import MagicMock

from langchain_core.documents import Document

from app.rag.chain import answer_static_question, format_docs


def test_format_docs_joins_page_content():
    docs = [Document(page_content="A"), Document(page_content="B")]
    assert format_docs(docs) == "A\n\nB"


def test_answer_static_question_uses_retrieved_context():
    docs = [Document(page_content="The parking is at 100 Main Street.")]
    retriever = MagicMock()
    retriever.invoke.return_value = docs

    llm = MagicMock()
    llm.invoke.return_value = MagicMock(content="It's at 100 Main Street.")

    answer = answer_static_question("Where is the parking?", retriever=retriever, llm=llm)

    retriever.invoke.assert_called_once_with("Where is the parking?")
    assert answer == "It's at 100 Main Street."

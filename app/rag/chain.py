from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

from app.config import settings
from app.rag.retriever import get_retriever

SYSTEM_PROMPT = """You are a helpful assistant for City Center Parking.
Answer the user's question using ONLY the context provided below.
If the context does not contain the answer, say you don't have that information
and suggest the user ask about parking hours, prices, availability, location,
or how to make a reservation.
Never invent personal information about any individual. Keep answers concise.

Context:
{context}
"""

_prompt = ChatPromptTemplate.from_messages(
    [
        ("system", SYSTEM_PROMPT),
        ("human", "{question}"),
    ]
)


def get_llm() -> ChatOpenAI:
    return ChatOpenAI(
        model=settings.openai_chat_model,
        api_key=settings.openai_api_key,
        temperature=0,
    )


def format_docs(docs) -> str:
    return "\n\n".join(doc.page_content for doc in docs)


def answer_static_question(question: str, retriever=None, llm=None) -> str:
    """Answer a general/static question (info, hours*, prices*, location,
    booking process) using retrieval-augmented generation over Qdrant.

    (*Note: hours/prices/availability are dynamic and are handled by the
    dynamic_service lookup instead; this chain is for the static knowledge.)
    """
    retriever = retriever or get_retriever()
    llm = llm or get_llm()

    docs = retriever.invoke(question)
    context = format_docs(docs)
    messages = _prompt.invoke({"context": context, "question": question})
    response = llm.invoke(messages)
    return response.content

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import AzureChatOpenAI

from app.config import settings
from app.rag.retriever import get_retriever

SYSTEM_PROMPT = """You are a helpful assistant for Parking Chatbot, which supports multiple parking
facilities (City Center Parking, Airport Parking, Railway Station Parking, Mall Parking).
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


def get_llm() -> AzureChatOpenAI:
    return AzureChatOpenAI(
        azure_deployment=settings.dial_chat_deployment,
        azure_endpoint=settings.dial_endpoint,
        api_version=settings.dial_api_version,
        api_key=settings.dial_api_key,
        temperature=0,
        timeout=settings.llm_request_timeout_seconds,
        max_retries=0,
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

import uuid

import requests
import streamlit as st

API_URL = "http://localhost:8000/chat"

st.set_page_config(page_title="City Center Parking Chatbot", page_icon="🅿️")
st.title("🅿️ City Center Parking Chatbot")
st.caption("Ask about hours, prices, availability, location, or make a reservation.")

if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())
if "history" not in st.session_state:
    st.session_state.history = []

for role, content in st.session_state.history:
    with st.chat_message(role):
        st.write(content)

user_input = st.chat_input("Type your message...")
if user_input:
    st.session_state.history.append(("user", user_input))
    with st.chat_message("user"):
        st.write(user_input)

    try:
        reply = requests.post(
            API_URL,
            json={"session_id": st.session_state.session_id, "message": user_input},
            timeout=30,
        )
        reply.raise_for_status()
        bot_message = reply.json()["response"]
    except requests.RequestException as exc:
        bot_message = f"Sorry, I couldn't reach the chatbot service ({exc})."

    st.session_state.history.append(("assistant", bot_message))
    with st.chat_message("assistant"):
        st.write(bot_message)

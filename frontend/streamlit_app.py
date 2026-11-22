import uuid

import requests
import streamlit as st

API_URL = "http://localhost:8000"

FACILITY_NAMES = ["City Center Parking", "Airport Parking", "Railway Station Parking", "Mall Parking"]

st.set_page_config(page_title="Parking Chatbot", page_icon="🅿️", layout="centered")
st.title("🅿️ Parking Chatbot")
st.caption("Ask about hours, prices, availability, location, or make a reservation.")
with st.sidebar:
    st.subheader("Facilities")
    for facility in FACILITY_NAMES:
        st.write(f"- {facility}")

if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())
if "history" not in st.session_state:
    st.session_state.history = []
if "pending_request_id" not in st.session_state:
    st.session_state.pending_request_id = None

STATUS_LABELS = {
    "pending_admin_approval": ("⏳ Pending administrator approval", "info"),
    "approved": ("✅ Approved", "success"),
    "stored": ("✅ Approved & confirmed", "success"),
    "approved_pending_storage": ("✅ Approved (finalizing...)", "warning"),
    "rejected": ("❌ Rejected by administrator", "error"),
}


def render_status_banner():
    request_id = st.session_state.pending_request_id
    if not request_id:
        return
    try:
        resp = requests.get(f"{API_URL}/reservations/{request_id}", timeout=10)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException:
        st.info(f"Reservation #{request_id[:8]} status is temporarily unavailable.")
        return

    status = data.get("reservation_status") or "pending_admin_approval"
    label, kind = STATUS_LABELS.get(status, (status, "info"))
    message = f"Reservation #{request_id[:8]}: {label}"
    getattr(st, kind)(message)
    if status in ("stored", "rejected"):
        st.session_state.pending_request_id = None


render_status_banner()

for role, content in st.session_state.history:
    with st.chat_message(role):
        st.write(content)

user_input = st.chat_input("Type your message...")
if user_input:
    st.session_state.history.append(("user", user_input))
    with st.chat_message("user"):
        st.write(user_input)

    bot_message = None
    with st.spinner("Thinking..."):
        try:
            reply = requests.post(
                f"{API_URL}/chat",
                json={"session_id": st.session_state.session_id, "message": user_input},
                timeout=60,
            )
            reply.raise_for_status()
            data = reply.json()
            bot_message = data["response"]
            if data.get("request_id") and data.get("reservation_status") == "pending_admin_approval":
                st.session_state.pending_request_id = data["request_id"]
        except requests.RequestException as exc:
            bot_message = f"Sorry, I couldn't reach the chatbot service right now ({exc}). Please try again shortly."

    st.session_state.history.append(("assistant", bot_message))
    with st.chat_message("assistant"):
        st.write(bot_message)
    st.rerun()

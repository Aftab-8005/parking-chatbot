import requests
import streamlit as st

API_URL = "http://localhost:8000"

st.set_page_config(page_title="Parking Admin Dashboard", page_icon="🛡️", layout="wide")
st.title("🛡️ Parking Reservation — Administrator Dashboard")
st.caption("Review reservation requests submitted by the chatbot and approve or reject them.")


def fetch_requests(status: str | None) -> list[dict]:
    try:
        params = {"status": status} if status else {}
        resp = requests.get(f"{API_URL}/admin/requests", params=params, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException as exc:
        st.error(f"Could not reach the admin API: {exc}")
        return []


def decide(request_id: str, decision: str) -> None:
    try:
        resp = requests.post(
            f"{API_URL}/admin/requests/{request_id}/decision",
            json={"decision": decision},
            timeout=30,
        )
        resp.raise_for_status()
        body = resp.json()
        st.toast(f"Request #{request_id[:8]}: {body['status']} ({body.get('reservation_status')})")
    except requests.RequestException as exc:
        st.error(f"Decision failed: {exc}")


tab_pending, tab_approved, tab_rejected = st.tabs(["⏳ Pending", "✅ Approved", "❌ Rejected"])

with tab_pending:
    pending = fetch_requests("pending")
    if not pending:
        st.info("No pending reservation requests.")
    for req in pending:
        with st.container(border=True):
            detail_cols = st.columns(4)
            detail_cols[0].markdown(f"**Reference**\n\n#{req['request_id'][:8]}")
            detail_cols[1].markdown(f"**Customer**\n\n{req['first_name']} {req['last_name']}")
            detail_cols[2].markdown(f"**Vehicle**\n\n{req['car_number']}")
            detail_cols[3].markdown(f"**Facility**\n\n{req.get('facility') or 'N/A'}")

            detail_cols_2 = st.columns(3)
            detail_cols_2[0].markdown(f"**Start time**\n\n{req['start_time']}")
            detail_cols_2[1].markdown(f"**End time**\n\n{req['end_time']}")
            detail_cols_2[2].markdown(f"**Current status**\n\n{req['reservation_status'] or 'pending'}")

            action_cols = st.columns(2)
            if action_cols[0].button(
                "✅ Approve", key=f"approve-{req['request_id']}", use_container_width=True
            ):
                decide(req["request_id"], "approved")
                st.rerun()
            if action_cols[1].button(
                "❌ Reject", key=f"reject-{req['request_id']}", use_container_width=True
            ):
                decide(req["request_id"], "rejected")
                st.rerun()

def retry_storage(request_id: str) -> None:
    try:
        resp = requests.post(f"{API_URL}/admin/requests/{request_id}/retry-storage", timeout=30)
        resp.raise_for_status()
        body = resp.json()
        st.toast(f"Retry result for #{request_id[:8]}: {body.get('reservation_status')}")
    except requests.RequestException as exc:
        st.error(f"Retry failed: {exc}")


with tab_approved:
    approved = fetch_requests("approved")
    if not approved:
        st.info("No approved reservations yet.")
    for req in approved:
        with st.container(border=True):
            detail_cols = st.columns(4)
            detail_cols[0].markdown(f"**Reference**\n\n#{req['request_id'][:8]}")
            detail_cols[1].markdown(f"**Customer**\n\n{req['first_name']} {req['last_name']}")
            detail_cols[2].markdown(f"**Vehicle**\n\n{req['car_number']}")
            detail_cols[3].markdown(f"**Facility**\n\n{req.get('facility') or 'N/A'}")

            detail_cols_2 = st.columns(3)
            detail_cols_2[0].markdown(f"**Start time**\n\n{req['start_time']}")
            detail_cols_2[1].markdown(f"**End time**\n\n{req['end_time']}")
            detail_cols_2[2].markdown(f"**Storage status**\n\n{req['reservation_status']}")

            if req["reservation_status"] == "approved_pending_storage":
                if st.button("🔁 Retry storage", key=f"retry-{req['request_id']}"):
                    retry_storage(req["request_id"])
                    st.rerun()

with tab_rejected:
    rejected = fetch_requests("rejected")
    if not rejected:
        st.info("No rejected reservations.")
    for req in rejected:
        with st.container(border=True):
            detail_cols = st.columns(4)
            detail_cols[0].markdown(f"**Reference**\n\n#{req['request_id'][:8]}")
            detail_cols[1].markdown(f"**Customer**\n\n{req['first_name']} {req['last_name']}")
            detail_cols[2].markdown(f"**Vehicle**\n\n{req['car_number']}")
            detail_cols[3].markdown(f"**Facility**\n\n{req.get('facility') or 'N/A'}")

            detail_cols_2 = st.columns(3)
            detail_cols_2[0].markdown(f"**Start time**\n\n{req['start_time']}")
            detail_cols_2[1].markdown(f"**End time**\n\n{req['end_time']}")
            detail_cols_2[2].markdown(f"**Status**\n\n{req['reservation_status'] or 'rejected'}")

st.button("🔄 Refresh", on_click=st.rerun)

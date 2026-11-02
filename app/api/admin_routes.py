"""REST endpoints the human administrator uses to review and decide on
reservations (Stage 2).
"""

from __future__ import annotations

import logging
from datetime import datetime

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from app.database import dynamic_service

router = APIRouter(prefix="/admin", tags=["admin"])
logger = logging.getLogger("parking_chatbot.admin_api")

_ADMIN_PAGE_HTML = """<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>Parking Admin</title>
<style>
  body { font-family: -apple-system, Segoe UI, sans-serif; max-width: 760px; margin: 2rem auto; color: #1f2937; }
  h1 { font-size: 1.4rem; }
  table { width: 100%; border-collapse: collapse; margin-top: 1rem; }
  th, td { border: 1px solid #e5e7eb; padding: 8px 10px; text-align: left; font-size: 0.9rem; }
  th { background: #f9fafb; }
  button { border: none; padding: 6px 14px; border-radius: 4px; cursor: pointer; color: white; font-size: 0.85rem; }
  .approve { background: #16a34a; }
  .reject { background: #dc2626; margin-left: 6px; }
  .refresh { background: #2563eb; color: white; margin-top: 1rem; padding: 6px 14px; border-radius: 4px; border: none; cursor: pointer; }
  #status { margin-top: 1rem; min-height: 1.2rem; color: #374151; }
</style>
</head>
<body>
<h1>Parking Reservations - Admin Approval</h1>
<div id="status"></div>
<table>
  <thead><tr><th>ID</th><th>Name</th><th>Car</th><th>Start</th><th>End</th><th>Actions</th></tr></thead>
  <tbody id="rows"><tr><td colspan="6">Loading...</td></tr></tbody>
</table>
<button class="refresh" onclick="load()">Refresh</button>

<script>
async function load() {
  const res = await fetch('/admin/reservations/pending');
  const data = await res.json();
  const rows = document.getElementById('rows');
  rows.innerHTML = '';
  if (data.length === 0) {
    rows.innerHTML = '<tr><td colspan="6">No pending reservations.</td></tr>';
    return;
  }
  data.forEach(r => {
    const tr = document.createElement('tr');
    tr.innerHTML =
      '<td>' + r.id + '</td>' +
      '<td>' + r.first_name + ' ' + r.last_name + '</td>' +
      '<td>' + r.car_number + '</td>' +
      '<td>' + r.start_time + '</td>' +
      '<td>' + r.end_time + '</td>' +
      '<td><button class="approve" onclick="decide(' + r.id + ', \\'approved\\')">Approve</button>' +
      '<button class="reject" onclick="decide(' + r.id + ', \\'rejected\\')">Reject</button></td>';
    rows.appendChild(tr);
  });
}

async function decide(id, decision) {
  document.getElementById('status').innerText = 'Submitting...';
  try {
    const res = await fetch('/admin/reservations/' + id + '/decision', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({decision: decision})
    });
    const data = await res.json();
    if (res.ok) {
      document.getElementById('status').innerText = 'Reservation #' + id + ': ' + data.final_status;
    } else {
      document.getElementById('status').innerText = 'Error: ' + (data.detail || res.status);
    }
  } catch (e) {
    document.getElementById('status').innerText = 'Request failed: ' + e;
  }
  load();
}

load();
</script>
</body>
</html>
"""


class ReservationOut(BaseModel):
    id: int
    first_name: str
    last_name: str
    car_number: str
    start_time: str
    end_time: str
    status: str


class DecisionRequest(BaseModel):
    decision: str = Field(pattern="^(approved|rejected)$")


class DecisionResponse(BaseModel):
    reservation_id: int
    final_status: str


def _to_out(reservation: dict) -> ReservationOut:
    return ReservationOut(
        id=reservation["id"],
        first_name=reservation["first_name"],
        last_name=reservation["last_name"],
        car_number=reservation["car_number"],
        start_time=str(reservation["start_time"]),
        end_time=str(reservation["end_time"]),
        status=reservation["status"],
    )


@router.get("", response_class=HTMLResponse, include_in_schema=False)
def admin_page() -> str:
    """A minimal clickable admin page: lists pending reservations with
    Approve/Reject buttons that call the JSON endpoints below via fetch()."""
    return _ADMIN_PAGE_HTML


@router.get("/reservations/pending", response_model=list[ReservationOut])
def list_pending() -> list[ReservationOut]:
    return [_to_out(r) for r in dynamic_service.list_pending_reservations()]


@router.post("/reservations/{reservation_id}/decision", response_model=DecisionResponse)
def decide(reservation_id: int, request: DecisionRequest) -> DecisionResponse:
    reservation = dynamic_service.get_reservation(reservation_id)
    if reservation is None:
        raise HTTPException(status_code=404, detail="Reservation not found.")
    if reservation["status"] != "pending_admin_approval":
        raise HTTPException(
            status_code=409,
            detail=f"Reservation #{reservation_id} is not awaiting approval (status={reservation['status']}).",
        )

    dynamic_service.update_reservation_status(reservation_id, request.decision, decided_at=datetime.utcnow())

    return DecisionResponse(reservation_id=reservation_id, final_status=request.decision)

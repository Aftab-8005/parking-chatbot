"""A minimal MCP-style server (Stage 3) implemented with FastAPI.

Exposes a single tool, `write_reservation`, that appends a confirmed
reservation to a text file (see `mcp_server/storage.py`). This mirrors the
Model Context Protocol's tool-discovery/tool-call shape (`GET /mcp/tools`,
`POST /mcp/tools/{name}/call`) without pulling in the full MCP transport
stack, per the spec's explicit "develop a simple MCP server using Python +
FastAPI" fallback option.

Security:
  - Every call must present `Authorization: Bearer <MCP_API_KEY>` matching
    the shared secret configured on both sides (`app.config.settings.mcp_api_key`).
  - The output file path is fixed server-side; callers cannot supply a path,
    which rules out path traversal.
  - Field values are sanitized/length-limited in `storage.write_reservation`.
  - Internal errors are not leaked to the client (FastAPI's default
    exception handling already avoids that outside of debug mode).
"""

from __future__ import annotations

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel

from app.config import settings
from mcp_server.storage import InvalidReservationFieldError, write_reservation

app = FastAPI(title="Parking Reservation MCP Server")


def verify_token(authorization: str = Header(default="")) -> None:
    expected = f"Bearer {settings.mcp_api_key}"
    if not settings.mcp_api_key or authorization != expected:
        raise HTTPException(status_code=401, detail="Invalid or missing bearer token.")


class WriteReservationArgs(BaseModel):
    name: str
    car_number: str
    period: str
    approval_time: str


TOOLS = [
    {
        "name": "write_reservation",
        "description": "Append a confirmed parking reservation to the reservations file.",
        "input_schema": WriteReservationArgs.model_json_schema(),
    }
]


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/mcp/tools")
def list_tools(_: None = Depends(verify_token)) -> dict:
    return {"tools": TOOLS}


@app.post("/mcp/tools/write_reservation/call")
def call_write_reservation(args: WriteReservationArgs, _: None = Depends(verify_token)) -> dict:
    try:
        line = write_reservation(
            name=args.name,
            car_number=args.car_number,
            period=args.period,
            approval_time=args.approval_time,
        )
    except InvalidReservationFieldError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"status": "written", "line": line}

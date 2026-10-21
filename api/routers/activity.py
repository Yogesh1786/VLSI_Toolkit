"""Activity dashboard and visitor feedback.

On the hosted site visitors see totals only; details (file names, error messages,
feedback text) are shown in the local app, which reads the same database.
Set VT_SHOW_DETAILS=1 to show details on a hosted server too.
"""

import os
import re
import threading
import time

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field, field_validator

from vlsi_toolkit import activity, history, store

router = APIRouter(prefix="/api", tags=["Activity & feedback"])

FEEDBACK_LIMIT = 5            # messages per visitor address ...
FEEDBACK_WINDOW = 600         # ... per 10 minutes
_sent: dict[str, list[float]] = {}
_sent_lock = threading.Lock()


def details_allowed():
    return not history.hosted() or os.environ.get("VT_SHOW_DETAILS") == "1"


class FeedbackRequest(BaseModel):
    message: str = Field(..., min_length=3, max_length=2000)
    rating: int | None = Field(None, ge=1, le=5)
    name: str = Field("", max_length=80)
    email: str = Field("", max_length=120)
    page: str = Field("", max_length=100)

    @field_validator("message", "name", "email", "page")
    @classmethod
    def strip(cls, v: str) -> str:
        return v.strip()

    @field_validator("email")
    @classmethod
    def email_shape(cls, v: str) -> str:
        if v and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", v):
            raise ValueError("this does not look like an e-mail address")
        return v


def _throttle(client):
    now = time.time()
    with _sent_lock:
        times = [t for t in _sent.get(client, []) if now - t < FEEDBACK_WINDOW]
        if len(times) >= FEEDBACK_LIMIT:
            raise HTTPException(429, "Thanks! You have sent several messages already; please try again in a few minutes.")
        _sent[client] = times + [now]


@router.post("/feedback")
def send_feedback(req: FeedbackRequest, request: Request):
    if len(req.message) < 3:
        raise HTTPException(422, "Please write a short message.")
    # the address is used only for the in-memory rate limit, never stored
    _throttle(request.headers.get("x-forwarded-for", request.client.host if request.client else "?").split(",")[0])
    fid = store.get_store().add_feedback({"ts": time.time(), "message": req.message, "rating": req.rating,
                                          "name": req.name, "email": req.email, "page": req.page})
    return {"ok": True, "id": fid}


@router.get("/feedback")
def list_feedback(limit: int = Query(100, ge=1, le=500)):
    if not details_allowed():
        raise HTTPException(403, "Feedback messages are visible in the local app only.")
    return {"feedback": store.get_store().list_feedback(limit), "stats": store.get_store().feedback_stats()}


@router.get("/activity")
def get_activity(days: int = Query(30, ge=1, le=365)):
    s = store.get_store()
    result = activity.summary(days, s) | {"feedback": s.feedback_stats(), "details": details_allowed(),
                                         "database": store.public_info()}
    if result["details"]:
        result["recent"] = s.recent_events(40)
        result["failures"] = s.recent_events(20, failures_only=True)
    return result

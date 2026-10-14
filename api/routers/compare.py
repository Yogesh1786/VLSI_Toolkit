"""Tracking: compare two regression runs or two timing reports."""

from fastapi import APIRouter

from vlsi_toolkit import compare, timing_report

from ..models import CompareFileRequest, CompareFilesRequest
from .verification import analyze_logs

router = APIRouter(prefix="/api/compare", tags=["Tracking"])


@router.post("/regress")
def regressions(req: CompareFilesRequest):
    return compare.compare_regressions(analyze_logs(req.old), analyze_logs(req.new))


@router.post("/timing")
def timing(req: CompareFileRequest):
    old, new = timing_report.parse_report(req.old.text), timing_report.parse_report(req.new.text)
    if not old or not new:
        return {"error": "No timing paths found in one of the reports."}
    return compare.compare_timing(old, new)

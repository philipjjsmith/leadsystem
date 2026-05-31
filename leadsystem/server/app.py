"""
LeadSystem Web Server — FastAPI app.

Local:   python main.py serve
Render:  uvicorn server.app:app --host 0.0.0.0 --port $PORT
"""

import asyncio
import os
import re
import secrets
import sys
import json as _json
from datetime import date, datetime
from typing import Optional

# Ensure project root is importable regardless of how uvicorn loads this module
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from fastapi import BackgroundTasks, FastAPI, HTTPException, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from crm.database import (
    init_db, get_leads, get_lead, get_contact_log,
    update_lead, log_contact, get_pipeline_stats, get_follow_ups,
)
from scoring.lead_scorer import get_outreach_scripts
from crm.models import STATUS_CONFIG, STATUS_ORDER, TIER_CONFIG, METHOD_CONFIG, OUTCOME_CONFIG
from config import NICHES, FLORIDA_CITIES, GOOGLE_PLACES_API_KEY

# ── Paths ──────────────────────────────────────────────────────────────────────
STATIC_DIR   = os.path.join(os.path.dirname(__file__), "static")
TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "templates")
REPORTS_DIR  = os.path.join(PROJECT_ROOT, "output", "reports")
os.makedirs(REPORTS_DIR, exist_ok=True)

# ── App ────────────────────────────────────────────────────────────────────────
app = FastAPI(title="LeadSystem CRM", docs_url=None, redoc_url=None)
app.mount("/static",  StaticFiles(directory=STATIC_DIR),  name="static")
app.mount("/reports", StaticFiles(directory=REPORTS_DIR), name="reports")
templates = Jinja2Templates(directory=TEMPLATE_DIR)

# ── ANSI stripping ─────────────────────────────────────────────────────────────
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[mGKHFABCDJrs]")

def _strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text).strip()


# ── Scan state (module-level, single worker) ───────────────────────────────────
_scan_state: dict = {
    "running": False,
    "lines":   [],
    "done":    True,
    "error":   None,
    "city":    "",
    "niche":   "",
}
_scan_lock = asyncio.Lock()


async def _run_scan_task(city: str, niche: str, phone: str, no_website_only: bool) -> None:
    """Run the scan subprocess and stream output into _scan_state."""
    global _scan_state
    _scan_state = {
        "running": True,
        "lines":   [f"Starting scan: {niche} in {city}…"],
        "done":    False,
        "error":   None,
        "city":    city,
        "niche":   niche,
    }

    cmd = [
        sys.executable,
        os.path.join(PROJECT_ROOT, "main.py"),
        "scan",
        "--city",          city,
        "--niche",         niche,
        "--contact-phone", phone or "",
        "--auto-import",
    ]
    if no_website_only:
        cmd.append("--no-website-only")

    env = {
        **os.environ,
        "PYTHONUTF8": "1",
        "NO_COLOR":   "1",
        "TERM":       "dumb",
    }

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=PROJECT_ROOT,
            env=env,
        )

        async for raw_line in proc.stdout:
            text = raw_line.decode("utf-8", errors="replace")
            text = _strip_ansi(text)
            if text:
                _scan_state["lines"].append(text)

        await proc.wait()
        rc = proc.returncode
        if rc == 0:
            _scan_state["lines"].append("✓ Scan complete — leads imported to CRM.")
        else:
            _scan_state["lines"].append(f"⚠ Scan exited with code {rc}.")
            _scan_state["error"] = f"exit code {rc}"

    except Exception as exc:
        _scan_state["lines"].append(f"✗ Error: {exc}")
        _scan_state["error"] = str(exc)
    finally:
        _scan_state["running"] = False
        _scan_state["done"]    = True


# ── Startup ────────────────────────────────────────────────────────────────────
@app.on_event("startup")
def startup():
    init_db()


# ── Health check (UptimeRobot ping target) ─────────────────────────────────────
@app.get("/health")
async def health():
    return {"status": "ok"}


# ── Shared template context ────────────────────────────────────────────────────
def _ctx(active: str, **kw) -> dict:
    return {
        "active":         active,
        "today":          date.today().isoformat(),
        "STATUS_CONFIG":  STATUS_CONFIG,
        "STATUS_ORDER":   STATUS_ORDER,
        "TIER_CONFIG":    TIER_CONFIG,
        "METHOD_CONFIG":  METHOD_CONFIG,
        "OUTCOME_CONFIG": OUTCOME_CONFIG,
        **kw,
    }


def _parse(value, fallback):
    if isinstance(value, (dict, list)):
        return value
    try:
        return _json.loads(value or "null") or fallback
    except Exception:
        return fallback


# ── Routes ─────────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def root():
    return RedirectResponse("/dashboard")


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    stats      = get_pipeline_stats()
    follow_ups = get_follow_ups()
    today      = date.today().isoformat()
    overdue    = [f for f in follow_ups if (f.get("follow_up_date") or "") < today]
    due_today  = [f for f in follow_ups if (f.get("follow_up_date") or "") == today]
    top_leads  = get_leads()[:10]
    return templates.TemplateResponse(request, "dashboard.html", _ctx(
        "dashboard",
        stats=stats, overdue=overdue, due_today=due_today, top_leads=top_leads,
    ))


@app.get("/pipeline", response_class=HTMLResponse)
async def pipeline(
    request:    Request,
    status:     Optional[str] = None,
    tier:       Optional[int] = None,
    niche:      Optional[str] = None,
    no_website: Optional[str] = None,
):
    leads = get_leads(
        status=status or None,
        tier=tier or None,
        niche=niche or None,
        no_website=(no_website == "1"),
    )
    return templates.TemplateResponse(request, "pipeline.html", _ctx(
        "pipeline",
        leads=leads,
        filter_status=status or "",
        filter_tier=str(tier) if tier else "",
        filter_niche=niche or "",
        filter_no_website=no_website or "",
        total=len(leads),
    ))


@app.get("/leads/{lead_id}", response_class=HTMLResponse)
async def lead_detail(request: Request, lead_id: int, saved: str = None):
    lead = get_lead(lead_id)
    if not lead:
        return RedirectResponse("/pipeline")

    log             = get_contact_log(lead_id)
    score_breakdown = _parse(lead.get("score_breakdown"), {})
    website_issues  = _parse(lead.get("website_issues"), [])

    lead_for_scripts = dict(lead)
    lead_for_scripts["website_issues"]  = website_issues
    lead_for_scripts["score_breakdown"] = score_breakdown
    scripts = get_outreach_scripts(lead_for_scripts)

    safe = "".join(c if c.isalnum() or c in "- " else "_" for c in lead.get("name", ""))
    report_file = f"{safe.replace(' ', '_')[:40]}_{lead.get('warmth_score', 0)}.html"
    report_url  = f"/reports/{report_file}" if os.path.exists(
        os.path.join(REPORTS_DIR, report_file)
    ) else None

    return templates.TemplateResponse(request, "lead.html", _ctx(
        "pipeline",
        lead=lead, contact_log=log,
        score_breakdown=score_breakdown,
        website_issues=website_issues,
        scripts=scripts,
        report_url=report_url,
        saved=saved,
    ))


@app.post("/leads/{lead_id}/update")
async def lead_update(
    lead_id:        int,
    status:         str = Form(None),
    note:           str = Form(""),
    follow_up_date: str = Form(""),
    deal_value:     str = Form(""),
):
    lead = get_lead(lead_id)
    if not lead:
        return RedirectResponse("/pipeline", status_code=303)

    updates = {}

    if status and status in STATUS_ORDER:
        updates["status"] = status
        if status == "closed" and not lead.get("closed_at"):
            updates["closed_at"] = datetime.now().isoformat()

    if note and note.strip():
        existing = (lead.get("notes") or "").strip()
        stamp    = datetime.now().strftime("%Y-%m-%d")
        updates["notes"] = (existing + f"\n[{stamp}] {note.strip()}").strip()

    if follow_up_date and follow_up_date.strip():
        updates["follow_up_date"] = follow_up_date.strip()

    if deal_value and deal_value.strip():
        try:
            updates["deal_value"] = float(deal_value.replace("$", "").replace(",", ""))
        except ValueError:
            pass

    if updates:
        update_lead(lead_id, **updates)

    return RedirectResponse(f"/leads/{lead_id}?saved=1", status_code=303)


@app.post("/leads/{lead_id}/log")
async def lead_log(
    lead_id: int,
    method:  str = Form("call"),
    outcome: str = Form("no-answer"),
    notes:   str = Form(""),
):
    log_contact(lead_id, method, outcome, notes.strip())
    return RedirectResponse(f"/leads/{lead_id}?saved=1", status_code=303)


@app.get("/follow-ups", response_class=HTMLResponse)
async def followups_page(request: Request):
    all_fu    = get_follow_ups()
    today     = date.today().isoformat()
    overdue   = [l for l in all_fu if (l.get("follow_up_date") or "") <  today]
    due_today = [l for l in all_fu if (l.get("follow_up_date") or "") == today]
    upcoming  = [l for l in all_fu if (l.get("follow_up_date") or "") >  today]
    return templates.TemplateResponse(request, "followups.html", _ctx(
        "followups",
        overdue=overdue, due_today=due_today, upcoming=upcoming,
    ))


@app.get("/stats", response_class=HTMLResponse)
async def stats_page(request: Request):
    stats = get_pipeline_stats()
    return templates.TemplateResponse(request, "stats.html", _ctx(
        "stats", stats=stats,
    ))


# ── Run Scan page ──────────────────────────────────────────────────────────────

@app.get("/scan", response_class=HTMLResponse)
async def scan_page(request: Request):
    return templates.TemplateResponse(request, "scan.html", _ctx(
        "scan",
        cities=FLORIDA_CITIES,
        niches=NICHES,
        scan_running=_scan_state["running"],
        scan_lines=_scan_state["lines"],
        google_api_key=bool(GOOGLE_PLACES_API_KEY),
    ))


class ScanStartRequest(BaseModel):
    city:            str  = "Dunedin, FL"
    niche:           str  = "pressure_washing"
    phone:           str  = ""
    no_website_only: bool = False


@app.post("/scan/start")
async def scan_start(body: ScanStartRequest, background_tasks: BackgroundTasks):
    """Start a scan from the web UI (non-blocking — output streams via SSE)."""
    if _scan_state["running"]:
        return {"status": "busy", "message": "A scan is already running."}
    if not GOOGLE_PLACES_API_KEY:
        return {"status": "error", "message": "GOOGLE_PLACES_API_KEY not set."}

    background_tasks.add_task(
        _run_scan_task, body.city, body.niche, body.phone, body.no_website_only
    )
    return {"status": "started", "city": body.city, "niche": body.niche}


@app.get("/scan/stream")
async def scan_stream(request: Request):
    """Server-Sent Events — push scan output lines to the browser in real time."""
    async def event_gen():
        last_idx = 0
        while True:
            if await request.is_disconnected():
                break
            lines = _scan_state["lines"]
            while last_idx < len(lines):
                yield f"data: {lines[last_idx]}\n\n"
                last_idx += 1
            if _scan_state["done"] and last_idx >= len(_scan_state["lines"]):
                yield "data: [DONE]\n\n"
                break
            await asyncio.sleep(0.25)

    return StreamingResponse(event_gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ── Automated scan trigger (GitHub Actions / UptimeRobot) ──────────────────────

class ScanTriggerRequest(BaseModel):
    token:           str
    city:            str  = "Dunedin, FL"
    niche:           str  = "pressure_washing"
    phone:           str  = ""
    no_website_only: bool = False


@app.post("/scan/trigger")
async def scan_trigger(body: ScanTriggerRequest, background_tasks: BackgroundTasks):
    """
    Authenticated endpoint for automated scan triggering.
    Called by GitHub Actions daily.  Requires SCAN_TOKEN env var.
    """
    scan_token = os.environ.get("SCAN_TOKEN", "")
    if not scan_token:
        raise HTTPException(status_code=503, detail="SCAN_TOKEN not configured on server.")
    if not secrets.compare_digest(body.token, scan_token):
        raise HTTPException(status_code=401, detail="Invalid token.")
    if _scan_state["running"]:
        return {"status": "busy", "city": _scan_state["city"], "niche": _scan_state["niche"]}
    if not GOOGLE_PLACES_API_KEY:
        raise HTTPException(status_code=503, detail="GOOGLE_PLACES_API_KEY not configured.")

    background_tasks.add_task(
        _run_scan_task, body.city, body.niche, body.phone, body.no_website_only
    )
    return {"status": "started", "city": body.city, "niche": body.niche}

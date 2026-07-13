"""Stage 6 — Web app: upload + processing + human-in-the-loop review.

    uvicorn review.app:app --reload      ->  http://localhost:8000

Pages
  /            dépôt: drag-drop upload (images + PDF), QR pour téléphone,
               liste des documents avec statut en direct
  /m/{sid}     page téléphone (ouverte via le QR): photo ou fichier
  /review      bureau de vérification (l'UI de correction existante)

Processing
  every upload spawns `run_pipeline.py <file> --backend $PIPELINE_BACKEND`
  as a subprocess (crash-isolated from the server); progress is streamed
  from its log into the jobs list on the landing page.

Deployment
  designed to run in the provided Dockerfile on any container host.
  Set GEMINI_API_KEY (required — the deployed backend is gemini),
  optionally APP_PASSWORD (HTTP Basic gate on everything except the
  phone-upload URLs, whose unguessable session ids are their own auth)
  and PUBLIC_BASE_URL (https origin used inside the QR code when behind
  a proxy).

Review corrections append to data/corrections.jsonl — the fine-tuning
flywheel. Review effort is never wasted, it is training data.
"""
from __future__ import annotations

import base64
import json
import os
import re
import secrets
import socket
import subprocess
import sys
import time
from io import BytesIO
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parent.parent
RUNS = ROOT / "runs"
DATA = ROOT / "data"
UPLOADS = ROOT / "uploads"
STATIC = Path(__file__).resolve().parent / "static"

sys.path.insert(0, str(ROOT))
from pipeline.env import load_dotenv  # noqa: E402

load_dotenv()  # GEMINI_API_KEY / TESSERACT_CMD reach the pipeline subprocesses

BACKEND = os.environ.get("PIPELINE_BACKEND", "gemini")
ALLOWED_SUFFIXES = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp", ".pdf"}
MAX_UPLOAD_MB = 25

app = FastAPI(title="Gabon OCR")
RUNS.mkdir(exist_ok=True)
UPLOADS.mkdir(exist_ok=True)
app.mount("/files", StaticFiles(directory=RUNS), name="files")

# in-memory state (single-process server; survives requests, not restarts)
JOBS: dict[str, dict] = {}          # job_id -> {proc, log, started, source}
PHONE: dict[str, dict] = {}         # sid -> {created, job_id|None}


# ----------------------------------------------------------------------------
# optional password gate (deployed instances are public URLs)
# ----------------------------------------------------------------------------


@app.middleware("http")
async def _password_gate(request: Request, call_next):
    pw = os.environ.get("APP_PASSWORD")
    if pw:
        path = request.url.path
        # the phone pages authenticate by unguessable session id instead:
        # a QR scanned across devices cannot carry a Basic-auth header;
        # /healthz stays open for the host's health prober
        exempt = path.startswith("/m/") or path == "/api/upload" or path == "/healthz"
        if not exempt:
            header = request.headers.get("authorization", "")
            ok = False
            if header.startswith("Basic "):
                try:
                    decoded = base64.b64decode(header[6:]).decode(errors="ignore")
                    ok = secrets.compare_digest(decoded.split(":", 1)[-1], pw)
                except Exception:
                    ok = False
            if not ok:
                return Response(status_code=401,
                                headers={"WWW-Authenticate": 'Basic realm="gabon-ocr"'})
    return await call_next(request)


# ----------------------------------------------------------------------------
# pages
# ----------------------------------------------------------------------------


@app.get("/healthz")
def healthz():
    return {"ok": True}


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/review")
def review_page():
    return FileResponse(STATIC / "review.html")


@app.get("/m/{sid}")
def mobile_page(sid: str):
    if sid not in PHONE:
        raise HTTPException(410, "session expirée — re-scannez le QR code sur votre ordinateur")
    return FileResponse(STATIC / "mobile.html")


# ----------------------------------------------------------------------------
# upload -> pipeline job
# ----------------------------------------------------------------------------


def _slug(name: str) -> str:
    s = re.sub(r"[^A-Za-z0-9_-]+", "_", Path(name).stem).strip("_") or "document"
    return s[:40]


def _start_job(saved: Path, original_name: str) -> str:
    job_id = f"{_slug(original_name)}_{time.strftime('%Y%m%d_%H%M%S')}"
    n = 1
    while (RUNS / job_id).exists():
        n += 1
        job_id = f"{_slug(original_name)}_{time.strftime('%Y%m%d_%H%M%S')}_{n}"
    out_dir = RUNS / job_id
    out_dir.mkdir(parents=True)
    log_path = out_dir / "pipeline.log"
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUNBUFFERED": "1"}
    proc = subprocess.Popen(
        [sys.executable, "-u", str(ROOT / "run_pipeline.py"), str(saved),
         "--backend", BACKEND, "--out", str(out_dir)],
        cwd=str(ROOT),
        stdout=open(log_path, "w", encoding="utf-8"),
        stderr=subprocess.STDOUT,
        env=env,
    )
    JOBS[job_id] = {"proc": proc, "log": log_path, "started": time.time(),
                    "source": original_name}
    return job_id


@app.post("/api/upload")
async def upload(request: Request, file: UploadFile = File(...), sid: str | None = None):
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise HTTPException(415, f"format non supporté ({suffix or 'sans extension'}); "
                                 f"acceptés: {', '.join(sorted(ALLOWED_SUFFIXES))}")
    blob = await file.read()
    if len(blob) > MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(413, f"fichier trop volumineux (max {MAX_UPLOAD_MB} Mo)")
    if not blob:
        raise HTTPException(400, "fichier vide")

    saved = UPLOADS / f"{time.strftime('%Y%m%d_%H%M%S')}_{_slug(file.filename or 'doc')}{suffix}"
    saved.write_bytes(blob)
    job_id = _start_job(saved, file.filename or saved.name)

    if sid and sid in PHONE:
        PHONE[sid]["job_id"] = job_id
    return {"job_id": job_id}


def _job_status(job_id: str) -> dict:
    job = JOBS.get(job_id)
    report_ready = (RUNS / job_id / "report.json").exists()
    log_tail = ""
    log_p = (job["log"] if job else RUNS / job_id / "pipeline.log")
    if Path(log_p).exists():
        lines = Path(log_p).read_text(encoding="utf-8", errors="replace").strip().splitlines()
        log_tail = lines[-1] if lines else ""
        stages = [ln for ln in lines if ln.startswith("[")]
        if stages:
            log_tail = stages[-1]
    if job and job["proc"].poll() is None:
        status = "running"
    elif report_ready:
        status = "done"
    elif job and job["proc"].poll() not in (None, 0):
        status = "error"
        err = [ln for ln in Path(log_p).read_text(encoding="utf-8", errors="replace").splitlines()
               if ln.strip()][-3:] if Path(log_p).exists() else []
        log_tail = " | ".join(err)
    elif job:
        status = "done_no_report"   # e.g. backend none: localization QA only
    else:
        status = "done" if report_ready else "unknown"
    return {"job_id": job_id, "status": status, "stage": log_tail,
            "report_ready": report_ready,
            "review_url": f"/review?doc={job_id}" if report_ready else None}


@app.get("/api/job/{job_id}")
def job_status(job_id: str):
    if job_id not in JOBS and not (RUNS / job_id).exists():
        raise HTTPException(404, "job inconnu")
    return _job_status(job_id)


@app.get("/api/jobs")
def jobs_list():
    return [_job_status(j) for j in sorted(JOBS, key=lambda k: -JOBS[k]["started"])]


# ----------------------------------------------------------------------------
# phone (QR) sessions
# ----------------------------------------------------------------------------


def _lan_ip() -> str | None:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return None


def _public_base(request: Request) -> str:
    base = os.environ.get("PUBLIC_BASE_URL")
    if base:
        return base.rstrip("/")
    url = str(request.base_url).rstrip("/")
    # localhost is unreachable from a phone; swap in the LAN address
    if "localhost" in url or "127.0.0.1" in url:
        ip = _lan_ip()
        if ip:
            port = request.url.port or 8000
            url = f"http://{ip}:{port}"
    return url


@app.post("/api/phone-session")
def phone_session_create():
    sid = secrets.token_urlsafe(16)
    PHONE[sid] = {"created": time.time(), "job_id": None}
    # drop stale sessions (older than 2h)
    cutoff = time.time() - 7200
    for k in [k for k, v in PHONE.items() if v["created"] < cutoff]:
        PHONE.pop(k, None)
    return {"sid": sid}


@app.get("/api/phone-session/{sid}")
def phone_session_poll(sid: str):
    if sid not in PHONE:
        raise HTTPException(404, "session inconnue")
    return {"job_id": PHONE[sid]["job_id"]}


@app.get("/api/phone-session/{sid}/qr.svg")
def phone_session_qr(sid: str, request: Request):
    if sid not in PHONE:
        raise HTTPException(404, "session inconnue")
    import qrcode
    import qrcode.image.svg
    url = f"{_public_base(request)}/m/{sid}"
    img = qrcode.make(url, image_factory=qrcode.image.svg.SvgPathImage,
                      box_size=14, border=2)
    buf = BytesIO()
    img.save(buf)
    return Response(buf.getvalue(), media_type="image/svg+xml",
                    headers={"X-QR-Url": url})


# ----------------------------------------------------------------------------
# config surface for the frontend
# ----------------------------------------------------------------------------


def _opencrvs_configured() -> bool:
    return all(os.environ.get(k) for k in
               ("OPENCRVS_AUTH_URL", "OPENCRVS_GATEWAY_URL",
                "OPENCRVS_CLIENT_ID", "OPENCRVS_CLIENT_SECRET"))


@app.get("/api/config")
def config():
    return {
        "backend": BACKEND,
        "gemini_key_present": bool(os.environ.get("GEMINI_API_KEY")
                                   or os.environ.get("GOOGLE_API_KEY")),
        "max_upload_mb": MAX_UPLOAD_MB,
        "accepts": sorted(ALLOWED_SUFFIXES),
        "opencrvs_configured": _opencrvs_configured(),
    }


# ----------------------------------------------------------------------------
# OpenCRVS export
# ----------------------------------------------------------------------------


@app.post("/api/run/{doc_id}/opencrvs")
def send_to_opencrvs(doc_id: str):
    """Send a processed document to OpenCRVS as a prefilled birth notification."""
    if not _opencrvs_configured():
        raise HTTPException(503, "OpenCRVS non configuré (variables OPENCRVS_* manquantes)")
    rp = RUNS / doc_id / "report.json"
    if not rp.exists():
        raise HTTPException(404, f"no report for {doc_id}")
    from pipeline.opencrvs_export import send_report
    try:
        result = send_report(rp)
    except Exception as e:
        raise HTTPException(502, f"envoi OpenCRVS échoué: {e}")
    record = {
        "event_id": result["event_id"],
        "ts": int(time.time()),
        "prefilled": len(result["declaration"]),
        "prefilled_fields": sorted(result["declaration"].keys()),
    }
    (RUNS / doc_id / "opencrvs.json").write_text(
        json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return record


# ----------------------------------------------------------------------------
# review API (unchanged)
# ----------------------------------------------------------------------------


def _rel(p: str | None) -> str | None:
    if not p:
        return None
    return "/files/" + str(Path(p).resolve().relative_to(RUNS.resolve())).replace("\\", "/")


@app.get("/api/runs")
def runs():
    out = []
    for rp in sorted(RUNS.glob("*/report.json"), key=lambda p: -p.stat().st_mtime):
        r = json.loads(rp.read_text(encoding="utf-8"))
        ocrvs_p = rp.parent / "opencrvs.json"
        ocrvs = json.loads(ocrvs_p.read_text(encoding="utf-8")) if ocrvs_p.exists() else None
        out.append(
            {
                "doc_id": r["doc_id"],
                "status": r["status"],
                "review_count": len(r.get("fields_for_review", [])),
                "total": r.get("fields_total", 0),
                "corrected": (rp.parent / "corrected.json").exists(),
                "opencrvs": ocrvs,
            }
        )
    return out


@app.get("/api/run/{doc_id}")
def run_detail(doc_id: str):
    rp = RUNS / doc_id / "report.json"
    if not rp.exists():
        raise HTTPException(404, f"no report for {doc_id}")
    r = json.loads(rp.read_text(encoding="utf-8"))
    for name, f in r["fields"].items():
        f["crop_url"] = _rel(f.get("crop"))
    overlay = RUNS / doc_id / "field_boxes.png"
    r["overlay_url"] = _rel(str(overlay)) if overlay.exists() else None
    corrected = RUNS / doc_id / "corrected.json"
    r["corrected"] = json.loads(corrected.read_text(encoding="utf-8")) if corrected.exists() else None
    return r


class SavePayload(BaseModel):
    fields: dict[str, str | None]
    reviewer: str = "anonymous"


@app.post("/api/run/{doc_id}/save")
def save(doc_id: str, payload: SavePayload):
    rp = RUNS / doc_id / "report.json"
    if not rp.exists():
        raise HTTPException(404, f"no report for {doc_id}")
    r = json.loads(rp.read_text(encoding="utf-8"))

    corrected = {}
    changes = []
    ts = int(time.time())
    for name, f in r["fields"].items():
        new_val = payload.fields.get(name, f.get("value"))
        corrected[name] = new_val
        old_val = f.get("value")
        if (new_val or "") != (old_val or ""):
            changes.append(
                {
                    "doc": doc_id,
                    "field": name,
                    "crop": f.get("crop"),
                    "model_value": old_val,
                    "corrected_value": new_val,
                    "reviewer": payload.reviewer,
                    "ts": ts,
                }
            )

    (RUNS / doc_id / "corrected.json").write_text(
        json.dumps({"doc_id": doc_id, "reviewer": payload.reviewer, "ts": ts,
                    "fields": corrected}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    DATA.mkdir(exist_ok=True)
    with open(DATA / "corrections.jsonl", "a", encoding="utf-8") as fh:
        for c in changes:
            fh.write(json.dumps(c, ensure_ascii=False) + "\n")

    return JSONResponse({"saved": True, "changed_fields": len(changes)})

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

import asyncio

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
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

# the OpenCRVS client (localhost:3000 by default) calls /api/opencrvs/* from
# its own origin — a plain browser fetch needs this to not be blocked. Scoped
# to local dev origins only; not meant for a public deployment.
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1|\d+\.\d+\.\d+\.\d+):\d+",
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

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
# OpenCRVS in-form integration — the "scan here" panel on the declare pages
# (countryconfig fork, FieldType.FILE + FieldType.HTTP, see mosip.ts for the
# established pattern this mirrors). Both endpoints below are synchronous:
# they block until OCR finishes and hand back the declaration already
# shaped as V2 field ids, so each destination field's `value` formula can
# read straight off the response (field('page.ocr-fetch').get('data.child.dob'))
# with zero polling logic needed on the form side.
# ----------------------------------------------------------------------------

ANALYZE_TIMEOUT_S = 110  # keep a margin under the HTTP field's own timeout


def _nest(flat: dict) -> dict:
    """{"child.dob": v} -> {"child": {"dob": v}}.

    The declare form resolves a reference like
    field(x).get('data.fields.child.dob') by splitting on dots and walking
    the response with lodash `get`, so a flat key that itself contains dots
    is invisible to it. This nested copy is what the form reads;
    `declaration` stays flat for the notification API.
    """
    out: dict = {}
    for key, value in flat.items():
        parts = key.split(".")
        node = out
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node[parts[-1]] = value
    return out


def _declaration_payload(job_id: str) -> dict:
    """report.json -> the V2-field-id values the OpenCRVS form consumes."""
    from pipeline.opencrvs_export import build_declaration, enrich_birth_place

    report = json.loads((RUNS / job_id / "report.json").read_text(encoding="utf-8"))
    declaration, comments = build_declaration(report)
    enrich_birth_place(declaration, comments, report, run_dir=RUNS / job_id)
    return {
        "job_id": job_id,
        "declaration": declaration,
        "fields": _nest(declaration),
        "comment": "\n".join(comments),
        "review_url": f"/review?doc={job_id}",
    }


class MinioPathPayload(BaseModel):
    path: str  # FullDocumentPath OpenCRVS returned after the FILE field's own
               # upload, e.g. "/ocrvs/<eventId>/<uuid>.jpg"


def _minio_client():
    from minio import Minio
    return Minio(
        os.environ.get("OPENCRVS_MINIO_HOST", "localhost:3535"),
        access_key=os.environ.get("OPENCRVS_MINIO_ACCESS_KEY", "minioadmin"),
        secret_key=os.environ.get("OPENCRVS_MINIO_SECRET_KEY", "minioadmin"),
        secure=os.environ.get("OPENCRVS_MINIO_SECURE", "").lower() == "true",
    )


@app.post("/api/opencrvs/analyze")
async def opencrvs_analyze(payload: MinioPathPayload):
    """Desktop-upload path: the OpenCRVS FILE field uploads to OpenCRVS's own
    MinIO like any other document field (e.g. documents.proofOfBirth already
    does) — FieldType.HTTP can only send JSON, never raw file bytes, so we
    can't receive the upload directly. Instead an HTTP field sends us the
    resulting path and we fetch the bytes ourselves before running OCR."""
    m = re.match(r"^/([^/]+)/(.+)$", payload.path)
    if not m:
        raise HTTPException(400, f"chemin MinIO invalide: {payload.path!r}")
    bucket, key = m.group(1), m.group(2)
    suffix = Path(key).suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise HTTPException(415, f"format non supporté ({suffix or 'sans extension'})")

    try:
        client = _minio_client()
        blob = await asyncio.to_thread(
            lambda: client.get_object(bucket, key).read()
        )
    except Exception as e:
        raise HTTPException(502, f"lecture MinIO échouée: {e}")
    if not blob:
        raise HTTPException(400, "fichier vide")

    saved = UPLOADS / f"{time.strftime('%Y%m%d_%H%M%S')}_{_slug(Path(key).name)}{suffix}"
    saved.write_bytes(blob)
    job_id = _start_job(saved, Path(key).name)

    proc = JOBS[job_id]["proc"]
    try:
        await asyncio.wait_for(asyncio.to_thread(proc.wait), timeout=ANALYZE_TIMEOUT_S)
    except asyncio.TimeoutError:
        raise HTTPException(504, "analyse trop longue — réessayer ou ouvrir /review")
    if not (RUNS / job_id / "report.json").exists():
        raise HTTPException(502, "l'OCR a échoué — voir /review pour le détail")
    return _declaration_payload(job_id)


@app.get("/api/opencrvs/qr.svg")
def opencrvs_qr(request: Request):
    """QR shown inside the OpenCRVS declare form.

    The form panel embeds this at a fixed URL (a PARAGRAPH cannot build a
    dynamic one), so a session is minted per request here and the phone
    page it points at is the same /m/{sid} capture flow the OCR site uses.
    The form then collects the result through .../analyze/phone/latest.
    """
    import qrcode
    import qrcode.image.svg

    sid = secrets.token_urlsafe(16)
    PHONE[sid] = {"created": time.time(), "job_id": None}
    cutoff = time.time() - 7200
    for k in [k for k, v in PHONE.items() if v["created"] < cutoff]:
        PHONE.pop(k, None)

    url = f"{_public_base(request)}/m/{sid}"
    img = qrcode.make(url, image_factory=qrcode.image.svg.SvgPathImage,
                      box_size=11, border=2)
    buf = BytesIO()
    img.save(buf)
    return Response(
        buf.getvalue(),
        media_type="image/svg+xml",
        # each render must mint a fresh session, never reuse a cached image
        headers={"X-QR-Url": url, "Cache-Control": "no-store"},
    )


@app.get("/api/opencrvs/analyze/phone/latest")
async def opencrvs_analyze_phone_latest():
    """Collect whatever the phone most recently captured.

    The form's QR is a static URL, so the page cannot know which session id
    was minted for it; instead the registrar taps "j'ai photographié" and we
    return the newest phone capture. Scoped to the last 30 minutes so an old
    document can never leak into a fresh declaration.
    """
    def _newest_recent_sid() -> str | None:
        recent = [(v["created"], k) for k, v in PHONE.items()
                  if v.get("job_id") and v["created"] > time.time() - 1800]
        return max(recent)[1] if recent else None

    deadline = time.time() + ANALYZE_TIMEOUT_S
    while time.time() < deadline:
        sid = _newest_recent_sid()
        if sid:
            job_id = PHONE[sid]["job_id"]
            if (RUNS / job_id / "report.json").exists():
                return _declaration_payload(job_id)
            if job_id in JOBS and JOBS[job_id]["proc"].poll() not in (None, 0):
                raise HTTPException(502, "l'OCR a échoué — voir /review pour le détail")
        await asyncio.sleep(1.5)
    raise HTTPException(504, "aucune photo reçue du téléphone — scannez le QR puis réessayez")


@app.get("/api/opencrvs/analyze/phone/{sid}")
async def opencrvs_analyze_phone(sid: str):
    """QR/phone path: long-polls the phone session started by /api/phone-session
    until its upload (from /m/{sid}) has finished processing."""
    if sid not in PHONE:
        raise HTTPException(404, "session inconnue — réaffichez le QR")
    deadline = time.time() + ANALYZE_TIMEOUT_S
    job_id = None
    while time.time() < deadline:
        job_id = PHONE[sid].get("job_id")
        if job_id and (RUNS / job_id / "report.json").exists():
            return _declaration_payload(job_id)
        if job_id and job_id in JOBS and JOBS[job_id]["proc"].poll() not in (None, 0):
            raise HTTPException(502, "l'OCR a échoué — voir /review pour le détail")
        await asyncio.sleep(1.5)
    raise HTTPException(504, "toujours pas de photo reçue ou analyse trop longue")


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

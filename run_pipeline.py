#!/usr/bin/env python3
"""End-to-end runner: scan -> preprocess -> locate -> extract -> validate ->
score -> report. One directory per document under runs/.

Examples
--------
# stages 1-2 only (no model needed) - check localization quality first:
python run_pipeline.py scan.png --backend none

# local model via Ollama (pick any vision model you have pulled):
python run_pipeline.py scan.png --backend ollama --model glm-ocr
python run_pipeline.py scan.png --backend ollama --model qwen3-vl

# Gemini API (set GEMINI_API_KEY or pass --api-key):
python run_pipeline.py scan.png --backend gemini

# local model via vLLM (OpenAI-compatible):
python run_pipeline.py scan.png --backend openai \
    --base-url http://localhost:8000/v1 --model Qwen/Qwen3-VL-8B-Instruct

# no GPU? exercise validation/review with a fixture:
python run_pipeline.py scan.png --backend mock --fixture fixtures/volet_mere_2002.json
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from pipeline.env import load_dotenv

# Load .env (GEMINI_API_KEY, etc.) before anything reads os.environ.
load_dotenv()

from pipeline.confidence import build_report, score_fields
from pipeline.extract import run_extraction
from pipeline.countries import resolve as resolve_country
from pipeline.locate import locate, ocr_lines
from pipeline.preprocess import preprocess
from pipeline.validate import run_checks
from pipeline.vlm_client import MockClient, make_client
from pipeline.vlm_locate import vlm_locate


def main() -> None:
    # Windows consoles default to cp1252; validation messages may contain
    # characters it can't encode (e.g. '≠') — degrade to '?' instead of crashing
    import sys
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("input")
    ap.add_argument("--out", default=None, help="output dir (default runs/<stem>)")
    ap.add_argument("--backend", default="none",
                    choices=["none", "openai", "ollama", "gemini", "mock"])
    ap.add_argument("--model", default=None,
                    help="model id (default depends on backend)")
    ap.add_argument("--base-url", default=None)
    ap.add_argument("--fixture", default=None)
    ap.add_argument("--api-key", default=None, help="Gemini key (or set GEMINI_API_KEY)")
    ap.add_argument("--destamp", action="store_true",
                    help="also produce a stamp-suppressed variant")
    ap.add_argument("--country", default="auto",
                    help="country pack code (ga, tn, ...) or 'auto' to detect from the header")
    ap.add_argument("--countries-dir", default="config/countries")
    ap.add_argument("--locator", default="auto", choices=["auto", "template", "vlm"],
                    help="auto: template first, VLM grounding when unreliable (default); "
                         "template: never ground; vlm: always ground with the VLM")
    args = ap.parse_args()

    src = Path(args.input)
    out = Path(args.out or f"runs/{src.stem}")
    out.mkdir(parents=True, exist_ok=True)

    if src.suffix.lower() == ".pdf":
        from pipeline.pdfio import pdf_first_page_png
        png = out / "source_page1.png"
        n_pages = pdf_first_page_png(src, png)
        note = f" ({n_pages} pages, seule la page 1 est traitee)" if n_pages > 1 else ""
        print(f"      pdf -> {png.name}{note}")
        src = png

    print(f"[1/5] preprocess          -> {out}")
    pre = preprocess(src, out, destamp=args.destamp)
    print(f"      skew {pre.skew_deg:+.2f} deg, scale x{pre.scale:.2f}")

    print(f"[2/5] locate fields")
    import cv2
    lines = ocr_lines(cv2.imread(str(pre.enhanced_gray), 0))
    pack = resolve_country(args.country, " ".join(ln.text for ln in lines),
                           countries_dir=args.countries_dir)
    print(f"      country: {pack.name} ({pack.code})")
    loc = locate(pre.enhanced_gray, pre.enhanced_color, out,
                 templates_dir=pack.templates_dir)
    print(f"      template={loc.template_id} anchors={loc.anchors_found} "
          f"(+{loc.anchors_interpolated} interpolated) fields={len(loc.fields)} "
          f"reliable={loc.reliable}")
    print(f"      overlay: {loc.overlay_path}")
    if not loc.reliable:
        print("      !! template localization unreliable (new layout, multi-form page or bad scan).")
        if args.backend == "none" or args.locator == "template":
            print("      !! falling back to whole-page extraction; every field will be routed to review.")
            print("      !! a VLM backend (--backend gemini/ollama/openai) enables dynamic VLM grounding instead.")
        else:
            print("      !! will attempt dynamic VLM grounding before extraction.")

    if args.backend == "none":
        print("[3/5] extraction skipped (--backend none). Localization QA complete.")
        return

    print(f"[3/5] extract (two passes, backend={args.backend})")
    client = make_client(args.backend, model=args.model, base_url=args.base_url,
                         fixture=args.fixture, api_key=args.api_key)

    want_ground = args.locator == "vlm" or (args.locator == "auto" and not loc.reliable)
    if want_ground and not isinstance(client, MockClient):
        why = "forced by --locator vlm" if args.locator == "vlm" else "template unreliable"
        print(f"      locator: VLM grounding ({why})...")
        vloc = vlm_locate(client, pack.schema_path, loc, pre.enhanced_color,
                          pre.enhanced_gray, lines, out)
        if vloc is not None:
            loc = vloc
            # show per-region status
            audit_path = out / "vlm_locate_audit.json"
            if audit_path.exists():
                audit = json.loads(audit_path.read_text(encoding="utf-8"))
                for entry in audit.get("audit", []):
                    st = entry.get("status", "?")
                    sc = entry.get("score")
                    sc_str = f" ({sc})" if sc is not None else ""
                    print(f"        {entry.get('region', '?'):24s} {st}{sc_str}")
            print(f"      grounded {loc.grounded_kept}/{loc.grounded_total} regions "
                  f"({loc.grounded_verified} OCR-verified) -> crop pass re-enabled")
        else:
            print("      VLM grounding rejected (quorum or verification failed) -> page-only extraction")

    extraction = run_extraction(client, pack.schema_path, pre.enhanced_color, loc, out,
                                use_crops=loc.reliable, prompt_hint=pack.prompt_hint)

    print(f"[4/5] validate")
    findings = run_checks(extraction, places=pack.places, checks=pack.checks)
    for f in findings:
        if f.level != "ok":
            print(f"      {f.level.upper():4s} {f.field}: {f.message}")

    print(f"[5/5] score + report")
    scored = score_fields(extraction, findings)
    report = build_report(
        out.name, scored,   # = the runs/<dir> name, which the review API keys by
        {"country": pack.code, "template": loc.template_id, "locator": loc.locator,
         "anchors_found": loc.anchors_found,
         "anchors_interpolated": loc.anchors_interpolated,
         "vlm_regions_kept": loc.grounded_kept, "vlm_regions_verified": loc.grounded_verified},
        out,
    )
    print(f"      status: {report['status']} | auto-accepted "
          f"{report['fields_auto_accepted']}/{report['fields_total']}, "
          f"review: {', '.join(report['fields_for_review']) or 'none'}")
    print(f"      report: {out / 'report.json'}")
    print(f"      review UI: uvicorn review.app:app --reload  ->  http://localhost:8000")


if __name__ == "__main__":
    main()

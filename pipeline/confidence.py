"""Stage 5 — Confidence + routing: decide what a human must look at.

The 95%+ goal is a SYSTEM property, not a raw model property. The system hits
it by being honest about uncertainty: every field gets a score fused from
four independent signals, and anything below the bar goes to a human.

  score = 0.50 * model_confidence          (what the model believes)
        + 0.30 * agreement                 (page pass vs crop pass consensus)
        + 0.20 * validation                (did the checks corroborate it)
  then penalties: interpolated anchor -0.08, any WARN on the field -0.15,
  any FAIL caps the score at 0.40.

Routing:
  score >= 0.85           -> auto-accept  (green)
  0.60 <= score < 0.85    -> review       (amber)
  score <  0.60           -> review, flagged low (red)

Tune thresholds against YOUR error tolerance: raising the auto-accept bar
trades review workload for accuracy. Start strict, loosen with evidence.
"""
from __future__ import annotations

import json
from pathlib import Path

from .validate import Finding

AUTO_ACCEPT = 0.85
LOW = 0.60


def score_fields(extraction: dict, findings: list[Finding]) -> dict:
    by_field: dict[str, list[Finding]] = {}
    for f in findings:
        by_field.setdefault(f.field, []).append(f)

    out = {}
    for name, e in extraction.items():
        model_c = float(e.get("model_confidence") or 0.0)
        agree = e.get("agreement")
        agree_c = 1.0 if agree else (0.5 if agree is None else 0.0)

        fs = by_field.get(name, [])
        has_fail = any(f.level == "fail" for f in fs)
        has_warn = any(f.level == "warn" for f in fs)
        has_ok = any(f.level == "ok" for f in fs)
        valid_c = 0.0 if has_fail else (1.0 if has_ok and not has_warn else 0.5)

        s = 0.50 * model_c + 0.30 * agree_c + 0.20 * valid_c
        if e.get("anchor_interpolated"):
            s -= 0.08
        if has_warn:
            s -= 0.15
        if has_fail:
            s = min(s, 0.40)
        if e.get("value") in (None, ""):
            s = min(s, 0.30)  # empty values always deserve a look
        s = max(0.0, min(1.0, s))

        band = "high" if s >= AUTO_ACCEPT else ("medium" if s >= LOW else "low")
        out[name] = {
            **e,
            "score": round(s, 3),
            "band": band,
            "needs_review": band != "high",
            "findings": [f.as_dict() for f in fs],
        }
    return out


def build_report(doc_id: str, scored: dict, located_meta: dict, out_dir: str | Path) -> dict:
    n = len(scored)
    review = [k for k, v in scored.items() if v["needs_review"]]
    report = {
        "doc_id": doc_id,
        "status": "auto_accepted" if not review else "needs_review",
        "fields_total": n,
        "fields_auto_accepted": n - len(review),
        "fields_for_review": review,
        "localization": located_meta,
        "fields": scored,
    }
    Path(out_dir, "report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return report

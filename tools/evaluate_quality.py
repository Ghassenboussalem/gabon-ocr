#!/usr/bin/env python3
"""Extraction-quality metrics against the reference set in eval/ground_truth.json.

Complements tools/evaluate_batch.py, which measures throughput-style figures
(how much gets auto-accepted, how much reaches OpenCRVS) without needing
references. This one measures *correctness* against transcribed references,
using the metrics the document-AI literature actually relies on:

  ANLS        Average Normalized Levenshtein Similarity — the DocVQA/KIE
              standard. Tolerates a typo, collapses to 0 for a wrong answer.
              Reported with the customary 0.5 threshold.
  CER / WER   Character / word error rate, the OCR view of the same idea.
  Field P/R/F1  Treats extraction as retrieval: did we produce a value, and
              was it right? Exact and fuzzy (ANLS >= 0.8) variants, because
              exact match alone punishes an accent or a hyphen like a
              complete miss.
  Hallucination rate  Values invented for fields the act does not contain —
              the failure mode that matters most for a civil register.
  Schema conformance  Share of outputs that are valid against the target
              schema (ISO dates, OpenCRVS gender enum, well-formed names).

BLEU/ROUGE are deliberately not the headline: n-gram overlap rewards fluent
paraphrase and is blind to a wrong date, which is precisely the error class
that matters here. They are computed only for the free-text birthplace, as a
comparability baseline, and labelled as such.

    python tools/evaluate_quality.py
"""
from __future__ import annotations

import json
import re
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline.opencrvs_export import build_declaration  # noqa: E402

RUNS = ROOT / "runs"
EVAL = ROOT / "eval"
OUT_DIR = ROOT / "notes-superviseur"

# a value counts as "right enough" above this similarity: an accent or a
# hyphen should not score like a different person's name
FUZZY_THRESHOLD = 0.8
ANLS_THRESHOLD = 0.5   # the DocVQA convention

SCORED_FIELDS = ["child.name", "child.dob", "child.gender",
                 "father.name", "mother.name"]


# ---------------------------------------------------------------- helpers ---


def normalize(s: str) -> str:
    """Case, accent and whitespace folding.

    Applied to both sides before scoring: a register writes "Céline" and
    "CELINE" for the same person, and penalising that would measure
    typography rather than reading accuracy.
    """
    if s is None:
        return ""
    s = unicodedata.normalize("NFKD", str(s))
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"\s+", " ", s).strip().lower()
    return s


def levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def nls(pred: str, ref: str) -> float:
    """Normalized Levenshtein similarity in [0, 1]."""
    p, r = normalize(pred), normalize(ref)
    if not p and not r:
        return 1.0
    if not p or not r:
        return 0.0
    return 1.0 - levenshtein(p, r) / max(len(p), len(r))


def anls(pred: str, ref: str) -> float:
    """ANLS: similarity, floored to 0 below the threshold.

    The flooring is the point of the metric — a half-right name is not half
    a correct answer to a registrar, it is a wrong one.
    """
    score = nls(pred, ref)
    return score if score >= ANLS_THRESHOLD else 0.0


def cer(pred: str, ref: str) -> float:
    p, r = normalize(pred), normalize(ref)
    return levenshtein(p, r) / len(r) if r else (0.0 if not p else 1.0)


def wer(pred: str, ref: str) -> float:
    p, r = normalize(pred).split(), normalize(ref).split()
    if not r:
        return 0.0 if not p else 1.0
    # Levenshtein over word sequences
    prev = list(range(len(r) + 1))
    for i, wa in enumerate(p, 1):
        cur = [i]
        for j, wb in enumerate(r, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (wa != wb)))
        prev = cur
    return prev[-1] / len(r)


def ngrams(tokens: list[str], n: int) -> dict:
    out: dict = {}
    for i in range(len(tokens) - n + 1):
        key = tuple(tokens[i:i + n])
        out[key] = out.get(key, 0) + 1
    return out


def rouge_l(pred: str, ref: str) -> float:
    """ROUGE-L F1 (longest common subsequence)."""
    p, r = normalize(pred).split(), normalize(ref).split()
    if not p or not r:
        return 0.0
    dp = [[0] * (len(r) + 1) for _ in range(len(p) + 1)]
    for i in range(1, len(p) + 1):
        for j in range(1, len(r) + 1):
            dp[i][j] = dp[i - 1][j - 1] + 1 if p[i - 1] == r[j - 1] else max(dp[i - 1][j], dp[i][j - 1])
    lcs = dp[-1][-1]
    if not lcs:
        return 0.0
    prec, rec = lcs / len(p), lcs / len(r)
    return 2 * prec * rec / (prec + rec)


def bleu(pred: str, ref: str, max_n: int = 4) -> float:
    """Sentence BLEU with add-1 smoothing (short strings otherwise hit 0)."""
    p, r = normalize(pred).split(), normalize(ref).split()
    if not p or not r:
        return 0.0
    score = 1.0
    for n in range(1, max_n + 1):
        pg, rg = ngrams(p, n), ngrams(r, n)
        overlap = sum(min(c, rg.get(g, 0)) for g, c in pg.items())
        total = max(sum(pg.values()), 1)
        score *= (overlap + 1) / (total + 1)
    score **= 1 / max_n
    brevity = min(1.0, pow(2.718281828, 1 - len(r) / len(p))) if len(p) < len(r) else 1.0
    return score * brevity


def name_text(value) -> str:
    """A NAME field value -> the full name as written."""
    if isinstance(value, dict):
        return " ".join(x for x in [value.get("firstname", ""),
                                    value.get("surname", "")] if x).strip()
    return str(value or "")


def name_key(value) -> str:
    """Name reduced to its words, sorted.

    Acts order names differently by country — surname first in Nigeria and
    Benin, given name first elsewhere — so comparing the printed order would
    grade a typographic convention rather than reading accuracy. Slot
    correctness is measured separately by split_correct().
    """
    return " ".join(sorted(normalize(name_text(value)).split()))


def split_correct(pred, ref) -> bool:
    """Did firstname and surname each land in the right slot?

    This is the part OpenCRVS actually depends on: the two halves go into
    separate form fields, and swapping them is a real error even though the
    full name reads the same.
    """
    if not isinstance(pred, dict) or not isinstance(ref, dict):
        return False
    return (normalize(pred.get("firstname", "")) == normalize(ref.get("firstname", ""))
            and normalize(pred.get("surname", "")) == normalize(ref.get("surname", "")))


def flatten(value) -> str:
    return name_text(value) if isinstance(value, dict) else str(value or "")


# ------------------------------------------------------------ conformance ---


def schema_ok(field: str, value) -> bool:
    """Is the produced value usable by OpenCRVS as-is?"""
    if value in (None, ""):
        return True                       # absent is valid, just not filled
    if field == "child.dob":
        return bool(re.match(r"^\d{4}-\d{2}-\d{2}$", str(value)))
    if field == "child.gender":
        return value in ("male", "female")
    if field.endswith(".name"):
        return isinstance(value, dict) and bool(name_text(value).strip())
    return True


# ------------------------------------------------------------------ main ----


def evaluate_document(doc_id: str, ref_fields: dict) -> dict:
    report_path = RUNS / doc_id / "report.json"
    if not report_path.exists():
        return {"doc_id": doc_id, "missing": True}

    report = json.loads(report_path.read_text(encoding="utf-8"))
    declaration, _comments = build_declaration(report)

    per_field = {}
    for field in SCORED_FIELDS:
        ref = ref_fields.get(field)
        pred_raw = declaration.get(field)
        is_name = field.endswith(".name")

        pred = flatten(pred_raw)
        ref_s = name_text(ref) if is_name else str(ref or "")
        # names are matched on their words, not the act's printed order
        pred_cmp = name_key(pred_raw) if is_name else pred
        ref_cmp = name_key(ref) if is_name else ref_s

        has_ref = bool(ref_s.strip())
        has_pred = bool(pred.strip())

        entry = {
            "ref": ref_s,
            "pred": pred,
            "has_ref": has_ref,
            "has_pred": has_pred,
            "anls": anls(pred_cmp, ref_cmp) if has_ref and has_pred else 0.0,
            "nls": nls(pred_cmp, ref_cmp) if has_ref and has_pred else 0.0,
            "cer": cer(pred_cmp, ref_cmp) if has_ref else None,
            "wer": wer(pred_cmp, ref_cmp) if has_ref else None,
            "exact": has_ref and has_pred and normalize(pred_cmp) == normalize(ref_cmp),
            "split_ok": split_correct(pred_raw, ref) if is_name and has_ref and has_pred else None,
            "schema_ok": schema_ok(field, pred_raw),
            # a value produced for a field the act does not contain
            "hallucinated": (not has_ref) and has_pred,
        }
        entry["fuzzy"] = has_ref and has_pred and entry["nls"] >= FUZZY_THRESHOLD
        per_field[field] = entry

    # free-text birthplace: the one place where n-gram metrics are meaningful
    place_ref = str(ref_fields.get("birth_place") or "")
    place_pred = str((report.get("fields", {}).get("lieu_naissance") or {}).get("value") or "")
    place = {
        "ref": place_ref,
        "pred": place_pred,
        "anls": anls(place_pred, place_ref),
        "cer": cer(place_pred, place_ref),
        "rouge_l": rouge_l(place_pred, place_ref),
        "bleu": bleu(place_pred, place_ref),
    }

    return {"doc_id": doc_id, "missing": False, "fields": per_field, "place": place}


def aggregate(results: list[dict]) -> dict:
    scored = [r for r in results if not r["missing"]]
    entries = [e for r in scored for e in r["fields"].values()]

    with_ref = [e for e in entries if e["has_ref"]]
    without_ref = [e for e in entries if not e["has_ref"]]

    # retrieval view: a field is "retrieved" when we output something
    tp_exact = sum(1 for e in with_ref if e["exact"])
    tp_fuzzy = sum(1 for e in with_ref if e["fuzzy"])
    predicted = sum(1 for e in entries if e["has_pred"])
    expected = len(with_ref)

    def prf(tp: int) -> tuple:
        p = tp / predicted if predicted else 0.0
        r = tp / expected if expected else 0.0
        f = 2 * p * r / (p + r) if (p + r) else 0.0
        return p, r, f

    p_ex, r_ex, f_ex = prf(tp_exact)
    p_fz, r_fz, f_fz = prf(tp_fuzzy)

    answered = [e for e in with_ref if e["has_pred"]]
    places = [r["place"] for r in scored if r["place"]["ref"]]

    return {
        "documents": len(scored),
        "fields_expected": expected,
        "fields_predicted": predicted,
        "anls": sum(e["anls"] for e in with_ref) / expected if expected else 0.0,
        "anls_answered": sum(e["anls"] for e in answered) / len(answered) if answered else 0.0,
        "cer": sum(e["cer"] for e in answered) / len(answered) if answered else 0.0,
        "wer": sum(e["wer"] for e in answered) / len(answered) if answered else 0.0,
        "exact_precision": p_ex, "exact_recall": r_ex, "exact_f1": f_ex,
        "fuzzy_precision": p_fz, "fuzzy_recall": r_fz, "fuzzy_f1": f_fz,
        "coverage": len(answered) / expected if expected else 0.0,
        "hallucination_rate": (sum(1 for e in without_ref if e["hallucinated"]) / len(without_ref)
                               if without_ref else 0.0),
        "hallucination_slots": len(without_ref),
        "schema_conformance": sum(1 for e in entries if e["schema_ok"]) / len(entries) if entries else 0.0,
        "name_split_accuracy": (
            sum(1 for e in entries if e.get("split_ok") is True) /
            sum(1 for e in entries if e.get("split_ok") is not None)
            if any(e.get("split_ok") is not None for e in entries) else 0.0),
        "place_anls": sum(p["anls"] for p in places) / len(places) if places else 0.0,
        "place_cer": sum(p["cer"] for p in places) / len(places) if places else 0.0,
        "place_rouge_l": sum(p["rouge_l"] for p in places) / len(places) if places else 0.0,
        "place_bleu": sum(p["bleu"] for p in places) / len(places) if places else 0.0,
    }


def per_field_breakdown(results: list[dict]) -> dict:
    out = {}
    for field in SCORED_FIELDS:
        entries = [r["fields"][field] for r in results if not r["missing"]]
        with_ref = [e for e in entries if e["has_ref"]]
        answered = [e for e in with_ref if e["has_pred"]]
        out[field] = {
            "n": len(with_ref),
            "exact": sum(1 for e in with_ref if e["exact"]),
            "fuzzy": sum(1 for e in with_ref if e["fuzzy"]),
            "anls": sum(e["anls"] for e in with_ref) / len(with_ref) if with_ref else 0.0,
            "cer": sum(e["cer"] for e in answered) / len(answered) if answered else 0.0,
            "coverage": len(answered) / len(with_ref) if with_ref else 0.0,
        }
    return out


def main() -> None:
    gt = json.loads((EVAL / "ground_truth.json").read_text(encoding="utf-8"))
    docs = gt["documents"]

    results = [evaluate_document(doc_id, spec["fields"]) for doc_id, spec in docs.items()]
    missing = [r["doc_id"] for r in results if r["missing"]]
    agg = aggregate(results)
    breakdown = per_field_breakdown(results)

    payload = {
        "aggregate": agg,
        "per_field": breakdown,
        "per_document": [
            {
                "doc_id": r["doc_id"],
                "country": docs[r["doc_id"]]["country"],
                "anls": sum(e["anls"] for e in r["fields"].values() if e["has_ref"]) /
                        max(1, sum(1 for e in r["fields"].values() if e["has_ref"])),
                "exact": sum(1 for e in r["fields"].values() if e["exact"]),
                "expected": sum(1 for e in r["fields"].values() if e["has_ref"]),
                "place_anls": r["place"]["anls"],
            }
            for r in results if not r["missing"]
        ],
        "missing_documents": missing,
        "config": {
            "anls_threshold": ANLS_THRESHOLD,
            "fuzzy_threshold": FUZZY_THRESHOLD,
            "scored_fields": SCORED_FIELDS,
        },
    }

    EVAL.mkdir(exist_ok=True)
    (EVAL / "quality_metrics.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"{agg['documents']} documents, {agg['fields_expected']} champs de reference")
    if missing:
        print(f"  non traites: {', '.join(missing)}")
    print(f"  ANLS                 {agg['anls']:.3f}")
    print(f"  Exact match F1       {agg['exact_f1']:.3f}")
    print(f"  Fuzzy match F1       {agg['fuzzy_f1']:.3f}")
    print(f"  CER (repondus)       {agg['cer']:.3f}")
    print(f"  Couverture           {agg['coverage']:.3f}")
    print(f"  Hallucinations       {agg['hallucination_rate']:.3f}")
    print(f"  Conformite schema    {agg['schema_conformance']:.3f}")
    print(f"  Split prenom/nom     {agg['name_split_accuracy']:.3f}")
    print(f"-> {EVAL / 'quality_metrics.json'}")


if __name__ == "__main__":
    main()

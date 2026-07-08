#!/usr/bin/env python3
"""Exports.

1) CSV of golden records (corrected.json when present, else auto-accepted
   report values):
       python export.py csv --out data/actes.csv

2) Fine-tuning dataset from human corrections. Every reviewed field becomes
   one SFT sample: (crop image + instruction) -> corrected value. Formatted
   as chat messages, directly usable by common VLM SFT stacks (convert the
   image path per your framework's convention if needed):
       python export.py sft --out data/sft.jsonl

The flywheel: run pipeline -> review -> corrections.jsonl grows ->
export sft -> fine-tune the local model (LoRA is enough) -> accuracy rises ->
fewer fields routed to review. A few hundred corrected fields already make a
visible difference on a single handwriting style / form family.
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RUNS = ROOT / "runs"
DATA = ROOT / "data"

INSTRUCTION = (
    "Transcris la valeur manuscrite du champ '{field}' sur cet extrait d'acte "
    "de naissance gabonais. Réponds uniquement avec la valeur, sans commentaire."
)


def export_csv(out: Path) -> None:
    rows = []
    fieldnames: list[str] = ["doc_id", "status"]
    for rp in sorted(RUNS.glob("*/report.json")):
        r = json.loads(rp.read_text(encoding="utf-8"))
        corrected_p = rp.parent / "corrected.json"
        values = (
            json.loads(corrected_p.read_text(encoding="utf-8"))["fields"]
            if corrected_p.exists()
            else {k: v.get("value") for k, v in r["fields"].items()}
        )
        row = {"doc_id": r["doc_id"],
               "status": "corrected" if corrected_p.exists() else r["status"]}
        row.update(values)
        rows.append(row)
        for k in values:
            if k not in fieldnames:
                fieldnames.append(k)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {len(rows)} record(s) -> {out}")


def export_sft(out: Path) -> None:
    src = DATA / "corrections.jsonl"
    n = 0
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as w:
        if src.exists():
            for line in src.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                c = json.loads(line)
                if not c.get("crop") or c.get("corrected_value") in (None, ""):
                    continue
                sample = {
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {"type": "image", "image": c["crop"]},
                                {"type": "text",
                                 "text": INSTRUCTION.format(field=c["field"])},
                            ],
                        },
                        {"role": "assistant", "content": c["corrected_value"]},
                    ]
                }
                w.write(json.dumps(sample, ensure_ascii=False) + "\n")
                n += 1
    print(f"wrote {n} SFT sample(s) -> {out}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("what", choices=["csv", "sft"])
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    if a.what == "csv":
        export_csv(Path(a.out or DATA / "actes.csv"))
    else:
        export_sft(Path(a.out or DATA / "sft.jsonl"))

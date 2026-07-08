"""Stage 3 — Extraction: two passes + consensus.

  PASS 1 (page):  the whole enhanced page + the full schema -> one JSON.
                  The model sees global context (it can use the mother's
                  block to disambiguate the father's, read stamps, etc.)
  PASS 2 (crops): each located field crop -> a tiny targeted JSON.
                  The model sees ONLY the relevant strip, so it cannot drift
                  to a neighbouring line - this is where localization pays.

  CONSENSUS:      pass1 vs pass2 values are compared after normalization.
                  Agreement is a strong correctness signal; disagreement is
                  exactly what the human reviewer should look at.

Why not "just prompt the page"? Because on crowded forms page-level models
occasionally read the right value from the wrong line (father's date on the
mother's row). The crop pass makes that failure mode structurally impossible,
and the agreement bit turns two mediocre signals into one reliable one.
"""
from __future__ import annotations

import json
import unicodedata
from pathlib import Path

from rapidfuzz import fuzz

from .locate import LocateResult
from .vlm_client import MockClient, extract_json

SYSTEM = (
    "Tu es un agent d'état civil expert en lecture d'actes de naissance gabonais "
    "manuscrits. Tu transcris fidèlement, sans inventer. Si une valeur est "
    "illisible ou absente, tu réponds null. Tu réponds UNIQUEMENT en JSON valide, "
    "sans texte autour, sans balises markdown."
)

PAGE_PROMPT = """Voici un acte de naissance gabonais (volet). Extrais chaque champ.
Pour chaque champ, retourne un objet {{"raw": "<transcription exacte>", "value": "<valeur normalisée>", "confidence": <0.0-1.0>}}.
Règles de normalisation: dates -> "AAAA-MM-JJ" si déterminable (les dates en toutes lettres doivent être converties), heures -> "HH:MM", noms -> tels qu'écrits, NOM en majuscules puis prénoms. Champ vide ou illisible -> "value": null et "confidence" basse, mais "raw" garde ce qui est visible.
N'invente jamais une valeur non visible.

Champs à extraire (nom -> description):
{fields}

Réponds avec un unique objet JSON dont les clés sont exactement les noms de champs ci-dessus."""

CROP_PROMPT = """Cette image est découpée d'un acte de naissance gabonais. Elle contient la ou les valeurs manuscrites suivantes (l'étiquette imprimée peut être visible, ne la transcris pas):
{fields}
Retourne un objet JSON {{nom_du_champ: {{"raw": "...", "value": ..., "confidence": 0.0-1.0}}}} pour chaque champ listé. "value" null si illisible ou absent. Dates normalisées en AAAA-MM-JJ, heures en HH:MM. N'invente rien."""


def _norm_val(v) -> str:
    if v is None:
        return ""
    s = unicodedata.normalize("NFKD", str(v))
    s = "".join(c for c in s if not unicodedata.combining(c))
    return " ".join(s.lower().replace("-", " ").replace(".", " ").split())


def _fields_by_region(schema: dict) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for f in schema["fields"]:
        out.setdefault(f["from"], []).append(f)
    return out


def _coerce(obj) -> dict:
    """Model outputs are messy; coerce a field entry to {raw, value, confidence}."""
    if isinstance(obj, dict):
        return {
            "raw": obj.get("raw", "") or "",
            "value": obj.get("value", None),
            "confidence": float(obj.get("confidence", 0.5) or 0.0),
        }
    if obj is None:
        return {"raw": "", "value": None, "confidence": 0.0}
    return {"raw": str(obj), "value": str(obj), "confidence": 0.5}


def run_extraction(
    client,
    schema_path: str | Path,
    page_image: str | Path,
    located: LocateResult,
    out_dir: str | Path,
    prompt_hint: str = "",
    use_crops: bool = True,
) -> dict:
    out = Path(out_dir)
    schema = json.loads(Path(schema_path).read_text(encoding="utf-8"))
    by_region = _fields_by_region(schema)
    crop_by_region = {fb.name: fb for fb in located.fields}

    # ---------------- PASS 1: whole page ----------------
    if isinstance(client, MockClient):
        page = {k: _coerce(v) for k, v in client.fixture.get("page", {}).items()}
    else:
        listing = "\n".join(f'- {f["name"]}: {f["fr"]}' for f in schema["fields"])
        prompt = PAGE_PROMPT.format(fields=listing)
        if prompt_hint:
            prompt = prompt_hint + "\n\n" + prompt
        raw = client.chat(prompt, images=[page_image], system=SYSTEM,
                          max_tokens=8192, thinking_budget=2048)
        page = {k: _coerce(v) for k, v in extract_json(raw).items()}

    # ---------------- PASS 2: located crops ----------------
    crops: dict[str, dict] = {}
    regions_iter = by_region.items() if use_crops else []
    for region, fields in regions_iter:
        fb = crop_by_region.get(region)
        if fb is None or not fb.crop_path:
            continue
        if isinstance(client, MockClient):
            for f in fields:
                fx = client.fixture.get("fields", {}).get(f["name"])
                if fx is not None:
                    crops[f["name"]] = _coerce(fx)
            continue
        listing = "\n".join(f'- {f["name"]}: {f["fr"]}' for f in fields)
        try:
            prompt = CROP_PROMPT.format(fields=listing)
            if prompt_hint:
                prompt = prompt_hint + "\n\n" + prompt
            raw = client.chat(prompt, images=[fb.crop_path], system=SYSTEM,
                              max_tokens=4096, thinking_budget=1024)
            for k, v in extract_json(raw).items():
                crops[k] = _coerce(v)
        except Exception as e:  # a failed crop pass degrades gracefully to page-only
            for f in fields:
                crops.setdefault(f["name"], {"raw": "", "value": None, "confidence": 0.0,
                                             "error": str(e)})

    # ---------------- CONSENSUS ----------------
    merged: dict[str, dict] = {}
    for f in schema["fields"]:
        name = f["name"]
        p1 = page.get(name, {"raw": "", "value": None, "confidence": 0.0})
        p2 = crops.get(name)
        fb = crop_by_region.get(f["from"])

        if p2 is not None and (p2["value"] is not None or p1["value"] is None):
            chosen, source = p2, "crop"
        else:
            chosen, source = p1, "page"

        agree = None
        if p2 is not None and p1["value"] is not None and p2["value"] is not None:
            agree = fuzz.ratio(_norm_val(p1["value"]), _norm_val(p2["value"])) >= 90

        merged[name] = {
            "value": chosen["value"],
            "raw": chosen["raw"],
            "type": f["type"],
            "source": source,
            "page_value": p1["value"],
            "crop_value": p2["value"] if p2 else None,
            "model_confidence": round(
                (p1["confidence"] + p2["confidence"]) / 2 if p2 else p1["confidence"], 3
            ),
            "agreement": agree,
            "bbox": list(fb.bbox) if fb and use_crops else None,
            "crop": fb.crop_path if fb and use_crops else None,
            "anchor_interpolated": (fb.anchor_interpolated if fb else None) if use_crops else True,
        }

    (out / "extraction.json").write_text(
        json.dumps(merged, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return merged

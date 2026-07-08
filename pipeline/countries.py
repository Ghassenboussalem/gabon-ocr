"""Country packs — one directory per country under config/countries/<code>/:

    country.json    {"code","name","detect_keywords":[...],"checks":{...}}
    schema.json     the logical fields for that country's documents
    templates/      layout templates (anchors + geometry), auto-selected
    places.json     gazetteer used by the place validator

Auto-detection: each pack lists header phrases that identify its documents
("REPUBLIQUE TUNISIENNE", "République Gabonaise"). `resolve()` OCRs nothing
itself — pass it the OCR lines the locator produces anyway.

Adding a country = adding a directory. No code changes:
    1. put a clean specimen through `run_pipeline.py doc --backend none`
    2. `python tools/probe_labels.py runs/<doc>/enhanced_gray.png`
    3. write templates/<layout>.json from the probe (anchors + rel_y + fields)
    4. write schema.json, places.json, country.json
"""
from __future__ import annotations

import json
import unicodedata
from dataclasses import dataclass
from pathlib import Path


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return " ".join(s.lower().split())


@dataclass
class CountryPack:
    code: str
    name: str
    root: Path
    schema_path: Path
    templates_dir: Path
    places: list[str]
    checks: dict
    prompt_hint: str = ""

    @classmethod
    def load(cls, root: Path) -> "CountryPack":
        meta = json.loads((root / "country.json").read_text(encoding="utf-8"))
        places_p = root / "places.json"
        places = json.loads(places_p.read_text(encoding="utf-8")) if places_p.exists() else []
        return cls(
            code=meta["code"],
            name=meta.get("name", meta["code"]),
            root=root,
            schema_path=root / "schema.json",
            templates_dir=root / "templates",
            places=places,
            checks=meta.get("checks", {}),
            prompt_hint=meta.get("prompt_hint", ""),
        )


def list_countries(countries_dir: str | Path = "config/countries") -> dict[str, CountryPack]:
    out = {}
    for d in sorted(Path(countries_dir).iterdir()):
        if (d / "country.json").exists():
            pack = CountryPack.load(d)
            out[pack.code] = pack
    return out


def resolve(
    country: str, ocr_text: str, countries_dir: str | Path = "config/countries"
) -> CountryPack:
    packs = list_countries(countries_dir)
    if not packs:
        raise FileNotFoundError(f"no country packs under {countries_dir}")
    if country and country != "auto":
        if country not in packs:
            raise ValueError(f"unknown country {country!r}; available: {sorted(packs)}")
        return packs[country]

    text = _norm(ocr_text)
    scored: list[tuple[int, CountryPack]] = []
    for pack in packs.values():
        meta = json.loads((pack.root / "country.json").read_text(encoding="utf-8"))
        hits = sum(1 for kw in meta.get("detect_keywords", []) if _norm(kw) in text)
        if hits:
            scored.append((hits, pack))
    if scored:
        scored.sort(key=lambda t: -t[0])
        return scored[0][1]
    # nothing matched: use the generic pack (universal schema, page-level
    # extraction, everything routed to review) rather than guessing a country
    if "zz" in packs:
        return packs["zz"]
    return next(iter(packs.values()))

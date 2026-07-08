"""Stage 2b — VLM-grounded localization (dynamic, template-free fallback).

When the template gate says "this layout doesn't fit" (locate.reliable=False)
the pipeline used to give up on crops entirely. But the same VLM that reads
the page can also POINT at it: we ask for one bounding box per schema
*region* (the `from` values the crop pass consumes), so this works for every
country with zero layout calibration.

"Very reliable" is earned, not assumed — each box must survive three checks:

  sanity       clamped to the page; degenerate slivers and page-sized boxes
               are dropped (a box that covers everything localizes nothing)
  cross-check  the model also returns the first words it can read inside each
               box; the tesseract words already collected by stage 2 that
               fall inside the box must fuzzy-agree (using both partial_ratio
               and token_set_ratio for robustness):
                 agree      -> VERIFIED     trusted crop, scored normally
                 no OCR     -> UNVERIFIED   kept (handwriting zones OCR
                               text there    blind), but scored like an
                                             interpolated anchor -> penalty
                 disagree   -> CONTRADICTED dropped — a confident-wrong box
                                             is worse than no box
  quorum       if fewer than half the regions survive, or fewer than two are
               verified, the whole grounding attempt is discarded and the
               honest page-only fallback stands.

Surviving boxes become ordinary FieldBox crops: extraction's pass 2 re-reads
them and the page/crop consensus + confidence routing treat them exactly like
template crops (disagreement still routes to review — the last safety net).
Cost: one extra VLM call per document, only when templates fail.

Reliability features added in v2:
  - JSON repair pipeline (handled by vlm_client.extract_json)
  - Retry with decreasing thinking budget (up to MAX_ATTEMPTS)
  - Zoom-and-refine: failed regions get a targeted follow-up with a
    cropped view of the approximate area
  - Smarter cross-check: max(partial_ratio, token_set_ratio) so
    overlapping-but-different text fragments still verify
  - Full diagnostics: raw model output + audit always saved
"""
from __future__ import annotations

import json
from pathlib import Path

import cv2
from rapidfuzz import fuzz

from .locate import FieldBox, Line, LocateResult, _norm, save_field_crops
from .vlm_client import extract_json

GROUND_SYSTEM = (
    "Tu es un expert en analyse de mise en page de documents d'état civil. "
    "Tu localises des zones sur une page scannée. Tu réponds UNIQUEMENT en JSON "
    "valide, sans texte autour, sans balises markdown."
)

GROUND_PROMPT = """Voici la page scannée d'un acte d'état civil. Découpe-la en zones.
Pour chaque zone listée, donne le rectangle englobant le plus serré qui contient TOUT le contenu décrit (étiquettes imprimées ET valeurs manuscrites ou dactylographiées).

Zones (nom -> contenu attendu):
{regions}

Réponds UNIQUEMENT avec un objet JSON de la forme:
{{"nom_zone": {{"box_2d": [ymin, xmin, ymax, xmax], "text": "premiers mots visibles"}}}}
- box_2d: coordonnées normalisées de 0 à 1000 relatives à la page entière, ordre [ymin, xmin, ymax, xmax].
- "text": recopie exactement les 3 à 8 premiers mots lisibles à l'intérieur du rectangle.
- Si une zone n'existe pas sur cette page, omets sa clé. N'invente rien."""

GROUND_PROMPT_RETRY = """RAPPEL: tu dois répondre UNIQUEMENT en JSON valide. Pas de texte avant ou après. Pas de markdown.

""" + GROUND_PROMPT

REFINE_PROMPT = """Cette image est un recadrage (crop) de la page. Localise la zone suivante dans CE recadrage uniquement.
Zone : {name} — contient : {description}

Réponds UNIQUEMENT avec un objet JSON :
{{"{name}": {{"box_2d": [ymin, xmin, ymax, xmax], "text": "premiers mots visibles"}}}}
- box_2d : coordonnées normalisées 0-1000 RELATIVES À CE RECADRAGE.
- "text" : les 3 à 8 premiers mots lisibles dans le rectangle."""

# quorum: below these the grounding attempt is discarded entirely
MIN_KEPT_FRACTION = 0.5   # boxes surviving / regions requested
MIN_VERIFIED = 2          # boxes corroborated by OCR words

# cross-check thresholds (rapidfuzz, 0-100). Measured on real pairs:
# true matches score >=93 even through OCR noise, unrelated French phrases
# 40-50, OCR garbage vs handwriting ~27 — hence the wide safety band.
VERIFY_SCORE = 65         # >= : OCR corroborates the model's claimed text
CONTRADICT_SCORE = 50     # <  : OCR clearly reads something else -> drop
MIN_OCR_WORDS = 3         # ...but only when OCR read >=3 real words there;
                          # garbage tokens must yield "unverified", not a drop
MIN_OCR_WORDS_SMALL = 2   # for boxes shorter than SMALL_BOX_HEIGHT px
SMALL_BOX_HEIGHT = 80     # boxes below this height use the relaxed word count

MAX_ATTEMPTS = 3          # retries with decreasing thinking budget
THINKING_BUDGETS = [2048, 1024, 512]  # one per attempt


def _regions_from_schema(schema: dict) -> dict[str, list[str]]:
    """region name -> field descriptions, skipping page-level-only fields."""
    out: dict[str, list[str]] = {}
    for f in schema["fields"]:
        region = f.get("from", "page")
        if region and region != "page":
            out.setdefault(region, []).append(f.get("fr", f["name"]))
    return out


def _scale_box(box, page_w: int, page_h: int) -> tuple[int, int, int, int] | None:
    """[ymin,xmin,ymax,xmax] in 0-1000 -> clamped pixel (x,y,w,h), or None."""
    try:
        ymin, xmin, ymax, xmax = (float(v) for v in box)
    except (TypeError, ValueError):
        return None
    x1 = max(0, min(page_w - 1, int(xmin / 1000 * page_w)))
    x2 = max(0, min(page_w, int(xmax / 1000 * page_w)))
    y1 = max(0, min(page_h - 1, int(ymin / 1000 * page_h)))
    y2 = max(0, min(page_h, int(ymax / 1000 * page_h)))
    w, h = x2 - x1, y2 - y1
    if w < 30 or h < 12:                      # degenerate sliver
        return None
    if w * h > 0.65 * page_w * page_h:        # page-sized box localizes nothing
        return None
    return (x1, y1, w, h)


def _ocr_text_in_box(lines: list[Line], bbox: tuple[int, int, int, int]) -> str:
    """Concatenate OCR words whose center falls inside the box."""
    x, y, w, h = bbox
    words = []
    for ln in lines:
        for wd in ln.words:
            cx, cy = wd.x + wd.w / 2, wd.y + wd.h / 2
            if x <= cx <= x + w and y <= cy <= y + h:
                words.append(wd)
    words.sort(key=lambda wd: (wd.y // 20, wd.x))
    return " ".join(wd.text for wd in words)


def _cross_check_score(claimed: str, ocr_text: str) -> float:
    """Best fuzzy score between claimed VLM text and OCR text.

    Uses both partial_ratio (substring match — good when the VLM reads more
    text than OCR captured) and token_set_ratio (handles reordered/overlapping
    tokens — good when OCR and VLM read different fragments of the same box).
    """
    if not claimed or not ocr_text:
        return 0.0
    c, o = _norm(claimed), _norm(ocr_text)
    return max(
        fuzz.partial_ratio(c, o),
        fuzz.token_set_ratio(c, o),
    )


def _call_grounding(
    client, prompt: str, page_image, out_dir: Path, attempt: int,
    thinking_budget: int,
) -> dict | None:
    """Single grounding attempt. Returns parsed dict or None.

    Always saves the raw model output for diagnostics.
    """
    raw = "(request failed)"
    try:
        raw = client.chat(
            prompt, images=[page_image], system=GROUND_SYSTEM,
            max_tokens=8192, thinking_budget=thinking_budget,
        )
        # save raw response for every attempt (debug gold)
        (out_dir / f"vlm_locate_raw_{attempt}.txt").write_text(
            raw, encoding="utf-8",
        )
        return extract_json(raw)
    except Exception as e:
        (out_dir / f"vlm_locate_error_{attempt}.txt").write_text(
            f"{e}\n\n--- raw model output ---\n{raw}", encoding="utf-8",
        )
        return None


def _score_regions(
    parsed: dict, regions: dict[str, list[str]], lines: list[Line],
    page_w: int, page_h: int,
) -> tuple[list[FieldBox], list[dict], int, list[str]]:
    """Score parsed grounding response against OCR.

    Returns (fields, audit, n_verified, failed_region_names).
    """
    fields: list[FieldBox] = []
    audit: list[dict] = []
    n_verified = 0
    failed: list[str] = []

    for name in regions:
        entry = parsed.get(name)
        if not isinstance(entry, dict):
            audit.append({"region": name, "status": "missing_from_response"})
            failed.append(name)
            continue
        bbox = _scale_box(entry.get("box_2d"), page_w, page_h)
        if bbox is None:
            audit.append({"region": name, "status": "dropped_sanity"})
            failed.append(name)
            continue
        claimed = str(entry.get("text") or "")
        ocr_text = _ocr_text_in_box(lines, bbox)
        score = _cross_check_score(claimed, ocr_text)

        # adaptive OCR word threshold: small boxes (headers, single-line
        # fields) have fewer words to compare against
        min_words = MIN_OCR_WORDS_SMALL if bbox[3] < SMALL_BOX_HEIGHT else MIN_OCR_WORDS
        ocr_substantial = (
            sum(1 for w in ocr_text.split() if sum(c.isalpha() for c in w) >= 3) >= min_words
        )
        if ocr_substantial and claimed and score < CONTRADICT_SCORE:
            audit.append({"region": name, "status": "dropped_contradicted",
                          "claimed": claimed, "ocr": ocr_text[:80], "score": score})
            failed.append(name)
            continue
        verified = bool(claimed and ocr_text and score >= VERIFY_SCORE)
        n_verified += verified
        # unverified boxes ride the existing interpolated-anchor penalty:
        # they stay useful but their fields keep a review-leaning score
        fields.append(FieldBox(name, bbox, "vlm", anchor_interpolated=not verified))
        audit.append({"region": name, "status": "verified" if verified else "unverified",
                      "claimed": claimed, "ocr": ocr_text[:80], "score": round(score, 1)})

    return fields, audit, n_verified, failed


def _zoom_and_refine(
    client, failed_names: list[str], regions: dict[str, list[str]],
    page_color, page_w: int, page_h: int, lines: list[Line],
    out_dir: Path,
) -> tuple[list[FieldBox], list[dict], int]:
    """Targeted follow-up for regions that failed the initial grounding.

    For each failed region, send a cropped view of the approximate vertical
    band where we'd expect it (heuristic: divide the page into len(regions)
    equal strips).  This gives the model a zoomed-in view that's easier to
    localize precisely.

    Returns (extra_fields, extra_audit, extra_verified).
    """
    if not failed_names:
        return [], [], 0

    color = cv2.imread(str(page_color), cv2.IMREAD_COLOR)
    if color is None:
        return [], [], 0

    # order regions by schema position and estimate vertical bands
    all_names = list(regions.keys())
    n = len(all_names)
    strip_h = page_h // max(1, n)

    extra_fields: list[FieldBox] = []
    extra_audit: list[dict] = []
    extra_verified = 0

    for name in failed_names:
        idx = all_names.index(name) if name in all_names else 0
        # generous vertical crop: the strip for this region ± 30% overlap
        y_start = max(0, idx * strip_h - int(strip_h * 0.3))
        y_end = min(page_h, (idx + 1) * strip_h + int(strip_h * 0.3))
        crop = color[y_start:y_end, :, :]
        if crop.size == 0:
            continue

        # save the crop for debugging
        crop_path = out_dir / f"vlm_refine_crop_{name}.png"
        cv2.imwrite(str(crop_path), crop)

        description = "; ".join(regions[name])
        prompt = REFINE_PROMPT.format(name=name, description=description)
        raw = "(request failed)"
        try:
            raw = client.chat(
                prompt, images=[str(crop_path)], system=GROUND_SYSTEM,
                max_tokens=2048, thinking_budget=512,
            )
            parsed = extract_json(raw)
        except Exception as e:
            extra_audit.append({"region": name, "status": "refine_failed",
                                "error": str(e)})
            continue

        entry = parsed.get(name)
        if not isinstance(entry, dict):
            extra_audit.append({"region": name, "status": "refine_missing"})
            continue

        # coordinates are relative to the CROP — translate back to page
        crop_h, crop_w = crop.shape[:2]
        bbox_in_crop = _scale_box(entry.get("box_2d"), crop_w, crop_h)
        if bbox_in_crop is None:
            extra_audit.append({"region": name, "status": "refine_sanity_fail"})
            continue
        cx, cy, cw, ch = bbox_in_crop
        bbox = (cx, cy + y_start, cw, ch)  # translate y back to page space

        claimed = str(entry.get("text") or "")
        ocr_text = _ocr_text_in_box(lines, bbox)
        score = _cross_check_score(claimed, ocr_text)
        min_words = MIN_OCR_WORDS_SMALL if bbox[3] < SMALL_BOX_HEIGHT else MIN_OCR_WORDS
        ocr_substantial = (
            sum(1 for w in ocr_text.split() if sum(c.isalpha() for c in w) >= 3) >= min_words
        )
        if ocr_substantial and claimed and score < CONTRADICT_SCORE:
            extra_audit.append({"region": name, "status": "refine_contradicted",
                                "claimed": claimed, "ocr": ocr_text[:80], "score": score})
            continue
        verified = bool(claimed and ocr_text and score >= VERIFY_SCORE)
        extra_verified += verified
        extra_fields.append(FieldBox(name, bbox, "vlm", anchor_interpolated=not verified))
        extra_audit.append({"region": name, "status": f"refine_{'verified' if verified else 'unverified'}",
                            "claimed": claimed, "ocr": ocr_text[:80], "score": round(score, 1)})

    return extra_fields, extra_audit, extra_verified


def vlm_locate(
    client,
    schema_path: str | Path,
    prev: LocateResult,
    page_color: str | Path,
    page_gray: str | Path,
    lines: list[Line],
    out_dir: str | Path,
    min_crop_height: int = 96,
) -> LocateResult | None:
    """Ask the VLM for region boxes, verify them against OCR, build crops.

    Returns a new LocateResult (reliable, locator="vlm_grounded") or None if
    the attempt failed quorum — caller then keeps the page-only fallback.

    Reliability features:
      - Up to MAX_ATTEMPTS retries with decreasing thinking budget
      - Zoom-and-refine for regions that fail initial grounding
      - Multi-metric cross-check (partial_ratio + token_set_ratio)
      - Full diagnostic trail (raw output + audit) saved for every attempt
    """
    out = Path(out_dir)
    schema = json.loads(Path(schema_path).read_text(encoding="utf-8"))
    regions = _regions_from_schema(schema)
    if not regions:
        return None

    gray = cv2.imread(str(page_gray), 0)
    if gray is None:
        return None
    page_h, page_w = gray.shape[:2]

    listing = "\n".join(
        f"- {name}: contient: {'; '.join(descs)}" for name, descs in regions.items()
    )

    # --- retry loop: try up to MAX_ATTEMPTS with decreasing thinking budget ---
    best_result: tuple[list[FieldBox], list[dict], int, list[str]] | None = None
    for attempt in range(MAX_ATTEMPTS):
        budget = THINKING_BUDGETS[min(attempt, len(THINKING_BUDGETS) - 1)]
        prompt = GROUND_PROMPT.format(regions=listing) if attempt == 0 \
            else GROUND_PROMPT_RETRY.format(regions=listing)

        parsed = _call_grounding(client, prompt, page_color, out, attempt, budget)
        if parsed is None:
            continue

        fields, audit, n_verified, failed = _score_regions(
            parsed, regions, lines, page_w, page_h,
        )

        # is this attempt better than what we had?
        if best_result is None or len(fields) > len(best_result[0]):
            best_result = (fields, audit, n_verified, failed)

        # good enough to stop retrying?
        if (len(fields) >= max(1, round(MIN_KEPT_FRACTION * len(regions)))
                and n_verified >= MIN_VERIFIED):
            break

    if best_result is None:
        # all attempts failed to parse
        (out / "vlm_locate_audit.json").write_text(
            json.dumps({"accepted": False, "reason": "all_attempts_parse_failed",
                         "attempts": MAX_ATTEMPTS}, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return None

    fields, audit, n_verified, failed = best_result

    # --- zoom-and-refine for failed regions ---
    if failed:
        extra_fields, extra_audit, extra_verified = _zoom_and_refine(
            client, failed, regions, page_color, page_w, page_h, lines, out,
        )
        fields.extend(extra_fields)
        audit.extend(extra_audit)
        n_verified += extra_verified

    # --- quorum check ---
    if len(fields) < max(1, round(MIN_KEPT_FRACTION * len(regions))) or n_verified < MIN_VERIFIED:
        (out / "vlm_locate_audit.json").write_text(
            json.dumps({"accepted": False, "reason": "quorum_failed",
                         "regions_requested": len(regions),
                         "regions_kept": len(fields),
                         "regions_verified": n_verified,
                         "audit": audit}, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return None

    # --- success: build crops and overlay ---
    crops_dir = out / "crops"
    crops_dir.mkdir(parents=True, exist_ok=True)
    save_field_crops(fields, gray, crops_dir, min_crop_height)

    # refresh the QA overlay: green = OCR-verified box, orange = unverified
    color = cv2.imread(str(page_color), cv2.IMREAD_COLOR)
    overlay = color.copy() if color is not None else cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
    for fb in fields:
        x, y, w, h = fb.bbox
        col = (0, 170, 0) if not fb.anchor_interpolated else (0, 140, 255)
        cv2.rectangle(overlay, (x, y), (x + w, y + h), col, 2)
        cv2.putText(overlay, fb.name, (x + 3, max(12, y + 14)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, col, 1, cv2.LINE_AA)
    cv2.rectangle(overlay, (0, 0), (overlay.shape[1], 46), (160, 80, 0), -1)
    cv2.putText(overlay,
                "LOCALISATION VLM (template non fiable) - vert=verifie OCR, orange=non verifie",
                (12, 31), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2, cv2.LINE_AA)
    overlay_path = out / "field_boxes.png"
    cv2.imwrite(str(overlay_path), overlay)

    # always save the full audit (not just on rejection)
    (out / "vlm_locate_audit.json").write_text(
        json.dumps({"accepted": True,
                     "regions_requested": len(regions),
                     "regions_kept": len(fields),
                     "regions_verified": n_verified,
                     "audit": audit}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    # update locate.json in place so QA artifacts tell one coherent story
    loc_json_path = out / "locate.json"
    try:
        loc_json = json.loads(loc_json_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        loc_json = {}
    loc_json.update({
        "locator": "vlm_grounded",
        "template": prev.template_id,
        "template_reliable": False,
        "vlm_grounding": {
            "regions_requested": len(regions),
            "regions_kept": len(fields),
            "regions_verified": n_verified,
            "audit": audit,
        },
        "fields": [
            {"name": f.name, "bbox": list(f.bbox), "kind": f.kind,
             "interpolated_anchor": f.anchor_interpolated, "crop": f.crop_path}
            for f in fields
        ],
    })
    loc_json_path.write_text(
        json.dumps(loc_json, indent=2, ensure_ascii=False), encoding="utf-8",
    )

    return LocateResult(
        template_id=prev.template_id,
        fields=fields,
        anchors=prev.anchors,
        overlay_path=overlay_path,
        crops_dir=crops_dir,
        anchors_found=prev.anchors_found,
        anchors_interpolated=prev.anchors_interpolated,
        reliable=True,
        fit_residual_px=prev.fit_residual_px,
        field_coverage=prev.field_coverage,
        multi_form_slab=prev.multi_form_slab,
        locator="vlm_grounded",
        grounded_total=len(regions),
        grounded_kept=len(fields),
        grounded_verified=n_verified,
    )

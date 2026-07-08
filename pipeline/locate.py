"""Stage 2 — Field localization ("know the exact location").

Gabonese actes de naissance are PRINTED forms filled by hand. The printed
labels ("Date de Naissance", "Profession", ...) OCR reliably even when the
handwriting doesn't — so we use them as anchors:

  1. tesseract (fra) reads the page -> words + boxes
  2. words are grouped into lines; lines are fuzzy-matched against the anchor
     labels declared in a layout template (config/templates/*.json)
  3. anchors that OCR missed are interpolated from the template's nominal
     vertical positions (least-squares fit against the anchors we DID find)
  4. every schema field gets a bounding box, computed relative to its anchor:
       - "right_of": the dotted line to the right of a label
       - "band":     the strip between two anchors (multi-line values)
  5. field crops are cut from the enhanced grayscale image and an annotated
     overlay is drawn for visual QA / the review UI

Output boxes are in the coordinate space of the preprocessed images, so the
same box indexes enhanced_gray / enhanced_color / binary interchangeably.
"""
from __future__ import annotations

import json
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np
import os

import pytesseract
from pytesseract import Output

# Windows: point at the installed binary without touching PATH, e.g.
#   set TESSERACT_CMD=C:\Program Files\Tesseract-OCR\tesseract.exe
if os.environ.get("TESSERACT_CMD"):
    pytesseract.pytesseract.tesseract_cmd = os.environ["TESSERACT_CMD"]
from rapidfuzz import fuzz


def _resolve_tessdata() -> str | None:
    """Find a tessdata dir that actually contains fra.traineddata.

    System Tesseract installs frequently lack the French language pack, or
    ship a TESSDATA_PREFIX that points at the wrong directory. We check the
    env var first, then fall back to the copy bundled in the repo's tessdata/.
    Returns the dir to pass to tesseract via --tessdata-dir, or None to let
    tesseract use its own default.
    """
    candidates = []
    env = os.environ.get("TESSDATA_PREFIX")
    if env:
        candidates.append(Path(env))
    candidates.append(Path(__file__).resolve().parent.parent / "tessdata")
    for c in candidates:
        if (c / "fra.traineddata").exists():
            return str(c)
    return None


# Resolve once at import and export it, so tesseract (a subprocess) inherits
# a TESSDATA_PREFIX that actually has fra.traineddata — even if the system one
# was missing or wrong. Setting the env var (rather than a --tessdata-dir CLI
# arg) avoids Windows quoting issues with paths handed to the tesseract binary.
_TESSDATA_DIR = _resolve_tessdata()
if _TESSDATA_DIR:
    os.environ["TESSDATA_PREFIX"] = _TESSDATA_DIR

# ----------------------------------------------------------------------------
# OCR helpers
# ----------------------------------------------------------------------------


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return " ".join(s.lower().replace("'", "'").split())


@dataclass
class Word:
    x: int
    y: int
    w: int
    h: int
    text: str


@dataclass
class Line:
    words: list[Word]

    @property
    def bbox(self) -> tuple[int, int, int, int]:
        x1 = min(w.x for w in self.words)
        y1 = min(w.y for w in self.words)
        x2 = max(w.x + w.w for w in self.words)
        y2 = max(w.y + w.h for w in self.words)
        return x1, y1, x2 - x1, y2 - y1

    @property
    def text(self) -> str:
        return " ".join(w.text for w in self.words)


def ocr_lines(gray: np.ndarray, lang: str = "fra") -> list[Line]:
    d = pytesseract.image_to_data(gray, lang=lang, config="--psm 6", output_type=Output.DICT)
    grouped: dict[tuple, list[Word]] = {}
    for i in range(len(d["text"])):
        t = d["text"][i].strip()
        if not t or int(d["conf"][i]) < 15:
            continue
        key = (d["block_num"][i], d["par_num"][i], d["line_num"][i])
        grouped.setdefault(key, []).append(
            Word(d["left"][i], d["top"][i], d["width"][i], d["height"][i], t)
        )
    lines = [Line(sorted(ws, key=lambda w: w.x)) for ws in grouped.values()]
    return sorted(lines, key=lambda ln: ln.bbox[1])


# ----------------------------------------------------------------------------
# Anchor matching
# ----------------------------------------------------------------------------


@dataclass
class Anchor:
    id: str
    bbox: tuple[int, int, int, int]
    score: float
    matched_text: str
    interpolated: bool = False


def _best_span(line: Line, label: str) -> tuple[float, tuple[int, int, int, int], str]:
    """Best contiguous word-window in this line matching `label` (handles OCR
    noise inside a line, e.g. handwriting tokens glued to the printed label)."""
    n = max(1, len(label.split()))
    best = (0.0, line.bbox, line.text)
    words = line.words
    for size in range(max(1, n - 1), min(len(words), n + 2) + 1):
        for start in range(0, len(words) - size + 1):
            span = words[start : start + size]
            text = " ".join(w.text for w in span)
            score = fuzz.ratio(_norm(label), _norm(text))
            if score > best[0]:
                x1 = span[0].x
                y1 = min(w.y for w in span)
                x2 = span[-1].x + span[-1].w
                y2 = max(w.y + w.h for w in span)
                best = (score, (x1, y1, x2 - x1, y2 - y1), text)
    return best


def _enforce_order(found: dict[str, Anchor], template: dict) -> dict[str, Anchor]:
    """Anchors must appear in the template's vertical order. Keep the longest
    increasing (by y) subsequence over template order; matches that violate it
    (a label stolen by another form region or a stray hit) are dropped and
    later re-interpolated from the survivors."""
    order = [a["id"] for a in template["anchors"]]
    seq = [(order.index(k), found[k].bbox[1], k) for k in found if k in order]
    seq.sort()
    if len(seq) < 3:
        return found
    n = len(seq)
    lis = [1] * n
    prev = [-1] * n
    for i in range(n):
        for j in range(i):
            if seq[j][1] <= seq[i][1] and lis[j] + 1 > lis[i]:
                lis[i], prev[i] = lis[j] + 1, j
    end = max(range(n), key=lambda i: lis[i])
    keep = set()
    while end != -1:
        keep.add(seq[end][2])
        end = prev[end]
    return {k: v for k, v in found.items() if k in keep}


def _candidates(lines: list[Line], template: dict) -> list[tuple[float, str, int, tuple, str]]:
    """Score every (label, line) pair above threshold. Shared by column
    isolation and anchor assignment."""
    thresholds = template.get("match", {})
    min_long = thresholds.get("min_score", 78)
    min_short = thresholds.get("min_score_short", 85)
    labels = {a["label"] for a in template["anchors"]}
    out: list[tuple[float, str, int, tuple, str]] = []
    for label in labels:
        min_score = min_short if len(label) < 6 else min_long
        for li, line in enumerate(lines):
            score, bbox, text = _best_span(line, label)
            if score >= min_score:
                out.append((score, label, li, bbox, text))
    return out


def isolate_form_column(
    candidates: list[tuple], gray: np.ndarray
) -> tuple[list[tuple], tuple[int, int] | None]:
    """Carbon-copy sheets carry SEVERAL copies of the same printed form side
    by side (filled center + blank duplicates). Their labels are identical, so
    without this step a blank panel steals anchor occurrences and drags every
    field box sideways - and the y-residual reliability check cannot see it,
    because the panels share vertical structure.

    Cluster candidate label x-positions into columns; if more than one column
    looks like a form (>=4 distinct labels), keep the one whose slab contains
    the most ink (the filled copy) and drop candidates from the others.
    Returns (filtered_candidates, (slab_left, slab_right) or None).
    """
    if not candidates:
        return candidates, None
    page_h, page_w = gray.shape[:2]
    xs = sorted({c[3][0] for c in candidates})
    gap = max(40, int(page_w * 0.15))
    clusters: list[list[int]] = [[xs[0]]]
    for x in xs[1:]:
        if x - clusters[-1][-1] > gap:
            clusters.append([x])
        else:
            clusters[-1].append(x)

    def col_of(x: int) -> int:
        for i, cl in enumerate(clusters):
            if cl[0] <= x <= cl[-1]:
                return i
        return -1

    per_col: dict[int, list[tuple]] = {}
    for c in candidates:
        per_col.setdefault(col_of(c[3][0]), []).append(c)

    form_cols = {i: cs for i, cs in per_col.items() if len({c[1] for c in cs}) >= 4}
    if not form_cols:
        return candidates, None
    if len(form_cols) == 1:
        # single form on the page: still drop stray hits outside its column
        # (stamp text, marginal annotations) so they can't burn occurrence slots
        i = next(iter(form_cols))
        return [c for c in candidates if col_of(c[3][0]) == i], None

    # Several label columns. They are DUPLICATE COPIES of the form (carbon
    # sheets) only if they repeat the same labels; a single form whose anchors
    # sit at different x positions (mid-line phrases) must NOT be split.
    label_sets = {i: {c[1] for c in cs} for i, cs in form_cols.items()}
    ids = sorted(label_sets)
    duplicated = any(
        len(label_sets[a] & label_sets[b]) / max(1, min(len(label_sets[a]), len(label_sets[b]))) >= 0.5
        for k, a in enumerate(ids) for b in ids[k + 1:]
    )
    if not duplicated:
        return candidates, None

    ink = (gray < 140).astype(np.uint8)
    best_i, best_score, best_slab = None, -1.0, None
    order = sorted(form_cols)
    for pos, i in enumerate(order):
        left = max(0, clusters[i][0] - int(0.02 * page_w))
        nxt = clusters[order[pos + 1]][0] if pos + 1 < len(order) else page_w
        right = min(page_w, min(nxt - 4, clusters[i][-1] + int(0.45 * page_w)))
        slab = ink[:, left:right]
        ink_ratio = float(slab.mean()) if slab.size else 0.0
        labels_n = len({c[1] for c in form_cols[i]})
        score = labels_n * (0.25 + ink_ratio)
        if score > best_score:
            best_i, best_score, best_slab = i, score, (left, right)
    kept = [c for c in candidates if col_of(c[3][0]) == best_i]
    return kept, best_slab


def match_anchors(
    lines: list[Line], template: dict, candidates: list[tuple] | None = None
) -> dict[str, Anchor]:
    """Match template anchors against OCR lines.

    Global greedy assignment: all (label, line) candidate pairs are scored,
    then accepted best-score-first with each line span claimable once. This
    prevents confusable labels from stealing each other's lines (e.g. the
    header "ACTE DE NAISSANCE" fuzzy-matches "Date de Naissance" at ~94 —
    but the header label itself matches it at 100, so it claims the line
    first). Two labels may share a line if their x-spans barely overlap
    ("Sa légitime épouse (6)   Les parents (7)").
    Repeated labels (father/mother blocks) are then disambiguated by
    vertical order via `occurrence`.
    """
    if candidates is None:
        candidates = _candidates(lines, template)
    candidates = sorted(candidates, key=lambda c: -c[0])

    def _overlap(b1: tuple, b2: tuple) -> float:
        x1 = max(b1[0], b2[0])
        x2 = min(b1[0] + b1[2], b2[0] + b2[2])
        inter = max(0, x2 - x1)
        return inter / max(1, min(b1[2], b2[2]))

    claimed: dict[int, list[tuple]] = {}
    accepted: dict[str, list[tuple[float, tuple, str]]] = {}
    needed = {a["label"]: 0 for a in template["anchors"]}
    for a in template["anchors"]:
        needed[a["label"]] = max(needed[a["label"]], a.get("occurrence", 1))

    for score, label, li, bbox, text in candidates:
        if len(accepted.get(label, [])) >= needed[label]:
            continue
        if any(_overlap(bbox, prev) > 0.3 for prev in claimed.get(li, [])):
            continue
        claimed.setdefault(li, []).append(bbox)
        accepted.setdefault(label, []).append((score, bbox, text))

    found: dict[str, Anchor] = {}
    for a in template["anchors"]:
        occ = a.get("occurrence", 1)
        hits = sorted(accepted.get(a["label"], []), key=lambda h: h[1][1])
        if len(hits) >= occ:
            score, bbox, text = hits[occ - 1]
            found[a["id"]] = Anchor(a["id"], bbox, score, text)
    return _enforce_order(found, template)


def interpolate_missing(
    found: dict[str, Anchor], template: dict, page_w: int
) -> dict[str, Anchor]:
    """Anchors tesseract missed are recovered from the template's nominal
    relative-y positions: fit y = a*rel_y + b on the anchors we found, then
    predict the rest. x defaults to the form column's left edge."""
    xs = [an.bbox[0] for an in found.values()]
    hs = [an.bbox[3] for an in found.values()]
    col_left = int(np.percentile(xs, 20)) if xs else int(page_w * 0.05)
    med_h = int(np.median(hs)) if hs else 24

    rel = {a["id"]: a["rel_y"] for a in template["anchors"] if "rel_y" in a}
    pts = [(rel[k], found[k].bbox[1]) for k in found if k in rel]
    if len(pts) >= 2:
        r = np.array([p[0] for p in pts])
        y = np.array([p[1] for p in pts])
        A = np.vstack([r, np.ones_like(r)]).T
        (a_fit, b_fit), *_ = np.linalg.lstsq(A, y, rcond=None)
    else:
        a_fit, b_fit = None, None

    out = dict(found)
    for a in template["anchors"]:
        if a["id"] in out or "rel_y" not in a:
            continue
        if a_fit is None:
            continue
        y_pred = int(a_fit * a["rel_y"] + b_fit)
        label_w = int(len(a["label"]) * med_h * 0.55)
        out[a["id"]] = Anchor(
            a["id"], (col_left, y_pred, label_w, med_h), 0.0, "(interpolated)", True
        )
    return out


# ----------------------------------------------------------------------------
# Field geometry
# ----------------------------------------------------------------------------


@dataclass
class FieldBox:
    name: str
    bbox: tuple[int, int, int, int]
    kind: str
    anchor_interpolated: bool
    crop_path: str | None = None


def _column_bounds(anchors: dict[str, Anchor], page_w: int) -> tuple[int, int]:
    xs = [a.bbox[0] for a in anchors.values() if not a.interpolated]
    x2s = [a.bbox[0] + a.bbox[2] for a in anchors.values() if not a.interpolated]
    left = int(np.percentile(xs, 10)) if xs else int(page_w * 0.05)
    right = min(page_w - 4, (max(x2s) if x2s else page_w) + int(page_w * 0.08))
    return left, right


def compute_fields(
    anchors: dict[str, Anchor], template: dict, page_w: int, page_h: int,
    clamp: tuple[int, int] | None = None,
) -> list[FieldBox]:
    col_left, col_right = _column_bounds(anchors, page_w)
    if clamp:
        col_left = max(col_left, clamp[0])
        col_right = min(col_right, clamp[1])
    med_h = int(np.median([a.bbox[3] for a in anchors.values()])) if anchors else 24
    boxes: list[FieldBox] = []

    def anchor(aid: str) -> Anchor | None:
        return anchors.get(aid)

    for f in template["fields"]:
        kind = f["kind"]
        a = anchor(f["anchor"])
        if a is None:
            continue
        ax, ay, aw, ah = a.bbox
        interp = a.interpolated

        if kind == "right_of":
            nxt = anchor(f.get("until", ""))
            y1 = ay - int(0.7 * ah)
            y2 = (nxt.bbox[1] - 2) if nxt else ay + int(2.0 * ah)
            x1 = ax + aw + 4
            bbox = (x1, max(0, y1), max(10, col_right - x1), max(ah, y2 - y1))
        elif kind == "band":
            bot = anchor(f["until"])
            top = ay + (ah if not f.get("include_anchor_line", True) else -int(0.6 * ah))
            y2 = bot.bbox[1] - 2 if bot else min(page_h, ay + int(4 * ah))
            bbox = (col_left, max(0, top), col_right - col_left, max(ah, y2 - top))
        else:
            continue

        pad = f.get("pad", 4)
        x, y, w, h = bbox
        bbox = (
            max(0, x - pad),
            max(0, y - pad),
            min(page_w - max(0, x - pad), w + 2 * pad),
            min(page_h - max(0, y - pad), h + 2 * pad),
        )
        boxes.append(FieldBox(f["name"], bbox, kind, interp))
    return boxes


def save_field_crops(
    fields: list[FieldBox], gray: np.ndarray, crops_dir: Path, min_crop_height: int = 96
) -> None:
    """Cut each field box from the grayscale page and save it, upscaling small
    strips so they stay readable for a VLM. Sets crop_path on each FieldBox."""
    for fb in fields:
        x, y, w, h = fb.bbox
        crop = gray[y : y + h, x : x + w]
        if crop.size == 0:
            continue
        if crop.shape[0] < min_crop_height:
            s = min_crop_height / crop.shape[0]
            crop = cv2.resize(crop, None, fx=s, fy=s, interpolation=cv2.INTER_CUBIC)
        p = crops_dir / f"{fb.name}.png"
        cv2.imwrite(str(p), crop)
        fb.crop_path = str(p)


# ----------------------------------------------------------------------------
# Orchestration
# ----------------------------------------------------------------------------


@dataclass
class LocateResult:
    template_id: str
    fields: list[FieldBox]
    anchors: dict[str, Anchor]
    overlay_path: Path
    crops_dir: Path
    anchors_found: int = 0
    anchors_interpolated: int = 0
    reliable: bool = True
    fit_residual_px: float = 0.0
    field_coverage: float = 1.0
    multi_form_slab: tuple[int, int] | None = None
    locator: str = "template"          # "template" | "vlm_grounded"
    grounded_total: int = 0            # regions the VLM was asked to box
    grounded_kept: int = 0             # boxes that survived sanity + cross-check
    grounded_verified: int = 0         # boxes corroborated by OCR words


def detect_template(lines: list[Line], templates_dir: Path) -> dict:
    joined = _norm(" ".join(ln.text for ln in lines[:40]))
    candidates = sorted(templates_dir.glob("*.json"))
    for tpath in candidates:
        tpl = json.loads(tpath.read_text(encoding="utf-8"))
        kw = tpl.get("detect_keyword")
        if kw and _norm(kw) in joined:
            return tpl
    # fallback: first template without a detect keyword, else first template
    for tpath in candidates:
        tpl = json.loads(tpath.read_text(encoding="utf-8"))
        if not tpl.get("detect_keyword"):
            return tpl
    return json.loads(candidates[0].read_text(encoding="utf-8"))


def locate(
    enhanced_gray: str | Path,
    enhanced_color: str | Path,
    out_dir: str | Path,
    templates_dir: str | Path = "config/templates",
    min_crop_height: int = 96,
) -> LocateResult:
    out = Path(out_dir)
    crops_dir = out / "crops"
    crops_dir.mkdir(parents=True, exist_ok=True)

    gray = cv2.imread(str(enhanced_gray), 0)
    color = cv2.imread(str(enhanced_color), cv2.IMREAD_COLOR)
    page_h, page_w = gray.shape[:2]

    lines = ocr_lines(gray)
    template = detect_template(lines, Path(templates_dir))
    cands = _candidates(lines, template)
    cands, slab = isolate_form_column(cands, gray)
    anchors = match_anchors(lines, template, candidates=cands)
    n_found = len(anchors)

    # reliability: enough anchors, and their y-positions must fit the
    # template's nominal vertical layout (large residual = wrong form/column)
    rel = {a["id"]: a["rel_y"] for a in template["anchors"] if "rel_y" in a}
    pts = [(rel[k], anchors[k].bbox[1]) for k in anchors if k in rel]
    residual = 0.0
    if len(pts) >= 3:
        r = np.array([p_[0] for p_ in pts]); y = np.array([p_[1] for p_ in pts])
        A = np.vstack([r, np.ones_like(r)]).T
        (a_f, b_f), *_ = np.linalg.lstsq(A, y, rcond=None)
        residual = float(np.median(np.abs(a_f * r + b_f - y)))
    med_h = float(np.median([a.bbox[3] for a in anchors.values()])) if anchors else 24.0

    # Field-anchor coverage: how many of the anchors that actually bound the
    # field boxes were really FOUND (vs about to be interpolated). A template
    # can match on its header keyword and pass the residual check with a handful
    # of top-clustered header anchors, then place every body box by extrapolating
    # into an unanchored middle — this is exactly what happens when a document is
    # a different LAYOUT of a known type (e.g. Cote d'Ivoire free-narrative vs the
    # labeled-form the template was built on). Boxes drift onto the wrong lines
    # yet the gate says "reliable". Requiring most field-defining anchors to be
    # real makes the gate honest and generalizes to every country's templates.
    field_anchor_ids: set[str] = set()
    for f in template["fields"]:
        if f.get("anchor"):
            field_anchor_ids.add(f["anchor"])
        until = f.get("until")
        if until and until != "none":
            field_anchor_ids.add(until)
    real_field_anchors = sum(1 for aid in field_anchor_ids if aid in anchors)
    field_coverage = real_field_anchors / max(1, len(field_anchor_ids))

    match_cfg = template.get("match", {})
    min_found = match_cfg.get("min_anchors", 8)
    min_field_cov = match_cfg.get("min_field_coverage", 0.6)
    reliable = (
        n_found >= min_found
        and (len(pts) < 3 or residual <= 2.5 * med_h)
        and field_coverage >= min_field_cov
    )

    anchors = interpolate_missing(anchors, template, page_w)
    fields = compute_fields(anchors, template, page_w, page_h, clamp=slab)

    # save crops (upscaled so small dotted-line strips stay readable for a VLM)
    save_field_crops(fields, gray, crops_dir, min_crop_height)

    # annotated overlay for QA and the review UI
    overlay = color.copy()
    for fb in fields:
        x, y, w, h = fb.bbox
        col = (0, 170, 0) if not fb.anchor_interpolated else (0, 140, 255)
        cv2.rectangle(overlay, (x, y), (x + w, y + h), col, 2)
        cv2.putText(
            overlay, fb.name, (x + 3, max(12, y + 14)),
            cv2.FONT_HERSHEY_SIMPLEX, 0.45, col, 1, cv2.LINE_AA,
        )
    for an in anchors.values():
        x, y, w, h = an.bbox
        cv2.rectangle(overlay, (x, y), (x + w, y + h), (200, 40, 40), 1)
    if not reliable:
        cv2.rectangle(overlay, (0, 0), (overlay.shape[1], 46), (30, 30, 200), -1)
        cv2.putText(overlay, "LOCALISATION NON FIABLE - extraction page entiere, tout part en revue",
                    (12, 31), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2, cv2.LINE_AA)
    overlay_path = out / "field_boxes.png"
    cv2.imwrite(str(overlay_path), overlay)

    res = LocateResult(
        template_id=template["id"],
        fields=fields,
        anchors=anchors,
        overlay_path=overlay_path,
        crops_dir=crops_dir,
        anchors_found=n_found,
        anchors_interpolated=sum(1 for a in anchors.values() if a.interpolated),
        reliable=reliable,
        fit_residual_px=round(residual, 1),
        field_coverage=round(field_coverage, 2),
        multi_form_slab=slab,
    )
    (out / "locate.json").write_text(
        json.dumps(
            {
                "template": template["id"],
                "anchors_found": res.anchors_found,
                "anchors_interpolated": res.anchors_interpolated,
                "reliable": res.reliable,
                "fit_residual_px": res.fit_residual_px,
                "field_coverage": res.field_coverage,
                "multi_form_slab": list(slab) if slab else None,
                "fields": [
                    {
                        "name": f.name,
                        "bbox": f.bbox,
                        "kind": f.kind,
                        "interpolated_anchor": f.anchor_interpolated,
                        "crop": f.crop_path,
                    }
                    for f in fields
                ],
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return res


if __name__ == "__main__":
    import sys

    r = locate(sys.argv[1], sys.argv[2], sys.argv[3])
    print(f"template={r.template_id} anchors={r.anchors_found} interpolated={r.anchors_interpolated} "
          f"reliable={r.reliable} residual={r.fit_residual_px}px")
    print(f"fields={len(r.fields)} overlay={r.overlay_path}")

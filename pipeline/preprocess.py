"""Stage 1 — Preprocessing: make the words clearer before anything reads them.

Produces several coordinated variants of the input scan:
  enhanced_color.png  -> what the VLM sees (illumination-fixed, contrast-boosted, deskewed)
  enhanced_gray.png   -> high-contrast grayscale (field crops are cut from this)
  binary.png          -> adaptive-threshold binarization (ONLY for the anchor OCR,
                         never fed to the VLM - VLMs read natural images better)
  destamped_color.png -> optional variant with saturated blue/green stamp ink
                         suppressed (useful when stamps sit on top of handwriting)

All variants share the same geometry (same deskew, same scale), so a bounding
box found on one is valid on all of them. That property is what lets Stage 2
locate fields on the binary image and Stage 3 crop them from the enhanced one.
"""
from __future__ import annotations

import dataclasses
from pathlib import Path

import cv2
import numpy as np

# ----------------------------------------------------------------------------
# Individual operations
# ----------------------------------------------------------------------------


def upscale_if_small(img: np.ndarray, min_dim: int = 1600) -> tuple[np.ndarray, float]:
    """Old scans and phone photos are often tiny. Both tesseract and VLMs lose
    accuracy below ~1500px page width; upscale with cubic interpolation.
    Returns (image, scale_factor)."""
    h, w = img.shape[:2]
    longest = max(h, w)
    if longest >= min_dim:
        return img, 1.0
    scale = min(2.5, min_dim / longest)
    out = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    return out, scale


def normalize_illumination(gray: np.ndarray, kernel_frac: float = 0.06) -> np.ndarray:
    """Remove uneven lighting / paper yellowing by dividing by a heavily
    blurred copy of the image (the estimated background). This is the single
    most effective cleanup for faded old documents."""
    k = int(max(gray.shape) * kernel_frac) | 1  # odd kernel
    background = cv2.GaussianBlur(gray, (k, k), 0)
    background = np.clip(background, 1, 255)
    norm = cv2.divide(gray, background, scale=255)
    return norm.astype(np.uint8)


def clahe(gray: np.ndarray, clip: float = 2.5, tile: int = 8) -> np.ndarray:
    """Adaptive local contrast - lifts faint ink without blowing out the page."""
    return cv2.createCLAHE(clipLimit=clip, tileGridSize=(tile, tile)).apply(gray)


def binarize(gray: np.ndarray, block: int = 35, c: int = 15) -> np.ndarray:
    """Adaptive threshold. Used for skew estimation and anchor OCR."""
    return cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, block, c
    )


def detect_orientation(gray: np.ndarray) -> int:
    """Coarse 0/90/180/270 orientation by OCR yield: the correct orientation
    produces far more confidently-recognized text. tesseract's OSD is too
    unreliable on stamped/bilingual civil documents (it misreads scripts and
    reports ~0 confidence), so we measure instead of asking.

    Fast path: if the page already reads well upright, skip the other three
    rotations. A rotation must beat upright by a clear margin to win, so
    borderline noise never flips a readable page."""
    try:
        import pytesseract
        from pytesseract import Output
    except Exception:
        return 0
    small = gray
    if max(small.shape) > 1400:
        f = 1400 / max(small.shape)
        small = cv2.resize(small, None, fx=f, fy=f)

    def _yield(img: np.ndarray) -> int:
        try:
            d = pytesseract.image_to_data(img, lang="fra", config="--psm 6",
                                          output_type=Output.DICT)
        except Exception:
            return 0
        return sum(len(t.strip()) for t, c in zip(d["text"], d["conf"])
                   if t.strip() and int(c) >= 60)

    y0 = _yield(small)
    if y0 >= 150:
        return 0
    scores = {0: y0}
    for rot, code in ((90, cv2.ROTATE_90_CLOCKWISE), (180, cv2.ROTATE_180),
                      (270, cv2.ROTATE_90_COUNTERCLOCKWISE)):
        scores[rot] = _yield(cv2.rotate(small, code))
    best = max(scores, key=scores.get)
    if best != 0 and scores[best] > max(40, 1.3 * scores[0]):
        return best
    return 0


def apply_orientation(img: np.ndarray, rot: int) -> np.ndarray:
    if rot == 90:
        return cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE)
    if rot == 180:
        return cv2.rotate(img, cv2.ROTATE_180)
    if rot == 270:
        return cv2.rotate(img, cv2.ROTATE_90_COUNTERCLOCKWISE)
    return img


def estimate_skew(binary: np.ndarray, max_angle: float = 6.0) -> float:
    """Projection-profile deskew: try small rotations, keep the one where text
    rows are sharpest (row-ink-sum variance is maximal). Coarse-to-fine."""
    small = cv2.resize(binary, None, fx=0.4, fy=0.4, interpolation=cv2.INTER_NEAREST)
    ink = (255 - small).astype(np.float32)

    def score(angle: float) -> float:
        m = cv2.getRotationMatrix2D((small.shape[1] / 2, small.shape[0] / 2), angle, 1.0)
        r = cv2.warpAffine(ink, m, (small.shape[1], small.shape[0]), flags=cv2.INTER_NEAREST)
        profile = r.sum(axis=1)
        return float(profile.var())

    best_a, best_s = 0.0, score(0.0)
    for a in np.arange(-max_angle, max_angle + 0.01, 0.5):
        s = score(float(a))
        if s > best_s:
            best_a, best_s = float(a), s
    for a in np.arange(best_a - 0.5, best_a + 0.51, 0.1):
        s = score(float(a))
        if s > best_s:
            best_a, best_s = float(a), s
    return best_a


def rotate(img: np.ndarray, angle: float) -> np.ndarray:
    if abs(angle) < 0.05:
        return img
    h, w = img.shape[:2]
    m = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    border = 255 if img.ndim == 2 else (255, 255, 255)
    return cv2.warpAffine(img, m, (w, h), flags=cv2.INTER_CUBIC, borderValue=border)


def suppress_stamps(bgr: np.ndarray, sat_min: int = 55, val_min: int = 70) -> np.ndarray:
    """Attenuate saturated blue/green stamp ink so handwriting underneath
    survives. Official stamps are vivid (high saturation); faded pen strokes
    and pencil are not. Masked pixels are inpainted from surroundings.

    Use with judgement: if the handwriting itself is bright blue ballpoint,
    run the pipeline on BOTH this variant and enhanced_color and let the
    consensus step decide.
    """
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    h, s, v = cv2.split(hsv)
    hue_mask = ((h > 35) & (h < 135)).astype(np.uint8)  # green..blue range
    mask = hue_mask & (s > sat_min).astype(np.uint8) & (v > val_min).astype(np.uint8)
    mask = cv2.dilate(mask * 255, np.ones((3, 3), np.uint8), iterations=1)
    return cv2.inpaint(bgr, mask, inpaintRadius=3, flags=cv2.INPAINT_TELEA)


# ----------------------------------------------------------------------------
# Orchestration
# ----------------------------------------------------------------------------


@dataclasses.dataclass
class PreprocessResult:
    enhanced_color: Path
    enhanced_gray: Path
    binary: Path
    destamped_color: Path | None
    skew_deg: float
    scale: float
    orientation_deg: int = 0


def preprocess(
    image_path: str | Path,
    out_dir: str | Path,
    *,
    min_dim: int = 1600,
    destamp: bool = False,
) -> PreprocessResult:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    bgr = cv2.imread(str(image_path), cv2.IMREAD_COLOR)
    if bgr is None:
        raise FileNotFoundError(image_path)

    bgr, scale = upscale_if_small(bgr, min_dim=min_dim)

    # coarse orientation first (90/180/270); fine deskew comes later
    rot = detect_orientation(cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY))
    if rot:
        bgr = apply_orientation(bgr, rot)

    # grayscale cleanup chain
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    gray = cv2.medianBlur(gray, 3)  # photocopier salt-and-pepper speckle
    gray = normalize_illumination(gray)
    gray = clahe(gray)
    gray = cv2.fastNlMeansDenoising(gray, None, h=7, templateWindowSize=7, searchWindowSize=21)

    # deskew estimated once, applied to every variant so geometry stays shared
    angle = estimate_skew(binarize(gray))
    gray = rotate(gray, angle)
    bgr = rotate(bgr, angle)

    # color variant for the VLM: replace L channel with the cleaned gray
    lab = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB)
    l_chan, a_chan, b_chan = cv2.split(lab)
    l_norm = clahe(normalize_illumination(l_chan))
    enhanced_color = cv2.cvtColor(cv2.merge([l_norm, a_chan, b_chan]), cv2.COLOR_LAB2BGR)

    binary = binarize(gray)

    paths = PreprocessResult(
        enhanced_color=out / "enhanced_color.png",
        enhanced_gray=out / "enhanced_gray.png",
        binary=out / "binary.png",
        destamped_color=(out / "destamped_color.png") if destamp else None,
        skew_deg=angle,
        scale=scale,
        orientation_deg=rot,
    )
    cv2.imwrite(str(paths.enhanced_color), enhanced_color)
    cv2.imwrite(str(paths.enhanced_gray), gray)
    cv2.imwrite(str(paths.binary), binary)
    if destamp:
        cv2.imwrite(str(paths.destamped_color), suppress_stamps(enhanced_color))
    return paths


if __name__ == "__main__":
    import sys

    res = preprocess(sys.argv[1], sys.argv[2], destamp="--destamp" in sys.argv)
    print(f"skew={res.skew_deg:+.2f} deg  scale=x{res.scale:.2f}  orientation={res.orientation_deg}")
    print(f"wrote: {res.enhanced_color.parent}")

#!/usr/bin/env python3
"""Draw the end-to-end pipeline with the model used by each task.

What each stage really runs was read from the code (pipeline/*.py), not
assumed: classical computer vision and rules where no model is needed,
Tesseract for OCR, and the vision-language model (Gemini 2.5 Flash by default,
Qwen3-VL 8B as the local alternative) only where reading or reasoning over the
image is required.

    python tools/build_pipeline_image.py
    -> rapport/figures/pipeline_modeles.svg
    -> presentation/img/pipeline_modeles.png   (via typst)
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from build_report_figures import (AMBER, BLUE, GREY, LIGHT, NAVY, TEAL, BORDER, DEFS,
                                  arrow, esc, label, svg)

ROOT = Path(__file__).resolve().parent.parent
SVG_OUT = ROOT / "rapport" / "figures" / "pipeline_modeles.svg"
PNG_OUT = ROOT / "presentation" / "img" / "pipeline_modeles.png"

CLASSIC, OCR, VLM = GREY, AMBER, BLUE

# (number, title, description lines, model headline, model sub, colour, kind)
STAGES = [
    ("1", "Prétraitement", ["redressement, éclairage,", "binarisation, suppression", "des tampons"],
     "OpenCV", "vision classique", CLASSIC, "sans modèle d'IA"),
    ("2", "Détection du pays", ["mots-clés de l'en-tête", "lus par OCR, puis", "choix du pack pays"],
     "Règles", "correspondance de mots-clés", CLASSIC, "sans modèle d'IA"),
    ("3", "Localisation", ["ancres du gabarit sur le", "texte OCR ; si couverture", "< 0,6, repérage par VLM"],
     "Tesseract", "repli : Gemini 2.5 Flash", OCR, "OCR + VLM de repli"),
    ("4", "Extraction", ["lecture de la page entière,", "puis de chaque recadrage ;", "consensus des deux passes"],
     "Gemini 2.5 Flash", "local : Qwen3-VL 8B", VLM, "modèle vision-langage"),
    ("5", "Validation", ["dates en toutes lettres,", "énumérations, lieux,", "score de confiance"],
     "Règles + RapidFuzz", "comparaison approchée", CLASSIC, "sans modèle d'IA"),
    ("6", "Export OpenCRVS", ["alias de champs, nom,", "nationalité ; lieu de naissance", "résolu si confiance ≥ 0,7"],
     "Gemini 2.5 Flash", "lieu de naissance seulement", VLM, "VLM + règles"),
]


def build() -> str:
    b = [DEFS]
    b.append(label(40, 38, "Pipeline de traitement et modèle utilisé pour chaque tâche", 24, NAVY, bold=True))
    b.append(label(40, 64, "Scan (image ou PDF)  →  déclaration OpenCRVS pré-remplie", 14, GREY))
    w, gap, x0, y0 = 270, 14, 40, 96
    for i, (num, title, desc, model, sub, col, kind) in enumerate(STAGES):
        x = x0 + i * (w + gap)
        # header
        b.append(f'<rect x="{x}" y="{y0}" width="{w}" height="58" rx="8" fill="{col}"/>')
        b.append(f'<circle cx="{x + 30}" cy="{y0 + 29}" r="17" fill="white"/>')
        b.append(f'<text x="{x + 30}" y="{y0 + 35}" text-anchor="middle" font-size="18" '
                 f'font-weight="bold" fill="{col}">{num}</text>')
        b.append(f'<text x="{x + 58}" y="{y0 + 36}" font-size="18" font-weight="bold" '
                 f'fill="white">{esc(title)}</text>')
        # description card
        b.append(f'<rect x="{x}" y="{y0 + 66}" width="{w}" height="118" rx="8" fill="{LIGHT}" '
                 f'stroke="{BORDER}" stroke-width="1.2"/>')
        for k, ln in enumerate(desc):
            b.append(label(x + 16, y0 + 100 + k * 26, ln, 15, "#2b333b"))
        # model chip
        b.append(f'<rect x="{x}" y="{y0 + 200}" width="{w}" height="98" rx="10" fill="white" '
                 f'stroke="{col}" stroke-width="3"/>')
        b.append(label(x + w / 2, y0 + 228, "MODÈLE", 11, col, anchor="middle", bold=True))
        b.append(label(x + w / 2, y0 + 258, model, 20, col, anchor="middle", bold=True))
        b.append(label(x + w / 2, y0 + 282, sub, 13, GREY, anchor="middle"))
        # kind
        b.append(label(x + w / 2, y0 + 326, kind, 13, col, anchor="middle", bold=True))
        if i < len(STAGES) - 1:
            b.append(arrow(x + w + 1, y0 + 29, x + w + gap - 1, y0 + 29))
    # legend
    ly = y0 + 372
    items = [(CLASSIC, "Traitement classique ou règles : déterministe, sans modèle d'IA"),
             (OCR, "OCR : Tesseract (reconnaissance de caractères)"),
             (VLM, "Modèle vision-langage : Gemini 2.5 Flash par défaut")]
    xx = 40
    for col, txt in items:
        b.append(f'<rect x="{xx}" y="{ly}" width="22" height="22" rx="5" fill="{col}"/>')
        b.append(label(xx + 32, ly + 17, txt, 14, "#2b333b"))
        xx += 32 + len(txt) * 7.4 + 36
    b.append(f'<rect x="40" y="{ly + 40}" width="1690" height="46" rx="8" fill="{LIGHT}" '
             f'stroke="{BORDER}" stroke-width="1.2"/>')
    b.append(label(58, ly + 69, "Le moteur est interchangeable (make_client) : Gemini, Ollama ou serveur "
                                "compatible OpenAI, par exemple Qwen3-VL 8B hébergé localement, sans changer le code.",
                   14, NAVY))
    return svg(1770, ly + 110, "\n".join(b))


def main() -> None:
    SVG_OUT.write_text(build(), encoding="utf-8")
    PNG_OUT.parent.mkdir(parents=True, exist_ok=True)
    tmp = ROOT / "presentation" / "_pm.typ"
    tmp.write_text('#set page(width: auto, height: auto, margin: 6pt)\n'
                   '#image("/rapport/figures/pipeline_modeles.svg", width: 1770pt)\n',
                   encoding="utf-8")
    subprocess.run(["typst", "compile", "--root", str(ROOT), "--format", "png", "--ppi", "110",
                    str(tmp), str(PNG_OUT)], check=True)
    tmp.unlink()
    print("->", SVG_OUT, "\n->", PNG_OUT)


if __name__ == "__main__":
    main()

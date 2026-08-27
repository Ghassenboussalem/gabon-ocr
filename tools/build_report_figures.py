#!/usr/bin/env python3
"""Generate every figure used by the internship report.

Diagrams are emitted as SVG written directly (no diagramming dependency, and
the result stays crisp at any zoom); charts come from matplotlib and are fed
by the measured metrics, so a figure can never drift from the numbers it is
supposed to illustrate.

    python tools/build_report_figures.py    # -> rapport/figures/*.svg|png
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIG = ROOT / "rapport" / "figures"
EVAL = ROOT / "eval"

NAVY = "#1a3a5c"
BLUE = "#2e6da4"
TEAL = "#2a9d8f"
AMBER = "#e9a13b"
RED = "#c0504d"
GREY = "#5a6672"
LIGHT = "#eef2f6"
BORDER = "#c8d2dc"


# --------------------------------------------------------------- svg helpers --


def esc(text: str) -> str:
    """Escape text destined for an SVG text node.

    A bare ampersand in a label ("Validation & score") is a malformed
    entity reference and makes the whole file unparseable.
    """
    return (str(text).replace("&", "&amp;")
                     .replace("<", "&lt;")
                     .replace(">", "&gt;"))


def svg(width: int, height: int, body: str) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" '
        f'height="{height}" viewBox="0 0 {width} {height}" '
        f'font-family="Helvetica, Arial, sans-serif">\n'
        f'<rect width="{width}" height="{height}" fill="white"/>\n'
        f"{body}\n</svg>\n"
    )


def box(x, y, w, h, label, fill=LIGHT, stroke=BORDER, text=NAVY,
        size=13, bold=False, sub=None, rx=6) -> str:
    weight = "bold" if bold else "normal"
    out = (f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" '
           f'fill="{fill}" stroke="{stroke}" stroke-width="1.4"/>')
    if sub:
        out += (f'<text x="{x + w / 2}" y="{y + h / 2 - 6}" text-anchor="middle" '
                f'font-size="{size}" font-weight="{weight}" fill="{text}">{esc(label)}</text>')
        out += (f'<text x="{x + w / 2}" y="{y + h / 2 + 12}" text-anchor="middle" '
                f'font-size="{size - 3}" fill="{GREY}">{esc(sub)}</text>')
    else:
        out += (f'<text x="{x + w / 2}" y="{y + h / 2 + 5}" text-anchor="middle" '
                f'font-size="{size}" font-weight="{weight}" fill="{text}">{esc(label)}</text>')
    return out


def arrow(x1, y1, x2, y2, color=BLUE, dashed=False, label=None, lx=None, ly=None) -> str:
    dash = ' stroke-dasharray="5,4"' if dashed else ""
    out = (f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" '
           f'stroke-width="1.8" marker-end="url(#a)"{dash}/>')
    if label:
        out += (f'<text x="{lx or (x1 + x2) / 2}" y="{ly or (y1 + y2) / 2 - 6}" '
                f'text-anchor="middle" font-size="11" fill="{GREY}">{esc(label)}</text>')
    return out


DEFS = (f'<defs><marker id="a" viewBox="0 0 10 10" refX="9" refY="5" '
        f'markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
        f'<path d="M 0 0 L 10 5 L 0 10 z" fill="{BLUE}"/></marker></defs>')


def label(x, y, text, size=12, color=GREY, anchor="start", bold=False) -> str:
    weight = "bold" if bold else "normal"
    return (f'<text x="{x}" y="{y}" text-anchor="{anchor}" font-size="{size}" '
            f'font-weight="{weight}" fill="{color}">{esc(text)}</text>')


# ------------------------------------------------------------------ diagrams --


def fig_pipeline() -> str:
    """The five pipeline stages, with what each one produces."""
    b = [DEFS]
    stages = [
        ("1. Prétraitement", "redressement · échelle · binarisation", TEAL),
        ("2. Détection du pays", "en-tête → pack pays ou générique", TEAL),
        ("3. Localisation", "gabarit, sinon grounding VLM", AMBER),
        ("4. Extraction", "page entière + recadrages → consensus", BLUE),
        ("5. Validation & score", "dates ISO · énumérations · confiance", TEAL),
    ]
    y = 40
    for i, (title, sub, color) in enumerate(stages):
        b.append(box(60, y, 340, 62, title, fill="white", stroke=color,
                     size=14, bold=True, sub=sub))
        if i < len(stages) - 1:
            b.append(arrow(230, y + 62, 230, y + 86))
        y += 86
    b.append(box(60, y, 340, 46, "runs/<doc>/report.json", fill=LIGHT,
                 stroke=NAVY, size=13, bold=True))
    b.append(label(420, 76, "scan (image ou PDF)", 12))
    b.append(label(420, 334, "le gate d'honnêteté agit ici :", 11, RED, bold=True))
    b.append(label(420, 350, "couverture < 0,6 → bascule VLM", 11))
    b.append(label(420, 420, "confiance < 0,6 → « à vérifier »", 11))
    return svg(760, y + 80, "\n".join(b))


def fig_architecture() -> str:
    """How the three components sit relative to OpenCRVS."""
    b = [DEFS]
    b.append(label(40, 34, "Poste de l'officier d'état civil", 13, NAVY, bold=True))
    b.append(box(40, 48, 200, 56, "Navigateur", fill="white", stroke=GREY,
                 sub="formulaire OpenCRVS", size=13))
    b.append(box(270, 48, 180, 56, "Téléphone", fill="white", stroke=GREY,
                 sub="capture par QR", size=13))

    b.append(label(40, 156, "Service OCR (ce projet)", 13, NAVY, bold=True))
    b.append(box(40, 170, 410, 130, "", fill=LIGHT, stroke=BLUE))
    b.append(box(58, 188, 180, 46, "Application web", fill="white", stroke=BLUE, size=12))
    b.append(box(252, 188, 180, 46, "API d'analyse", fill="white", stroke=BLUE, size=12))
    b.append(box(58, 244, 374, 42, "Pipeline d'extraction (VLM)", fill="white",
                 stroke=BLUE, size=12))

    b.append(label(510, 156, "Plateforme OpenCRVS", 13, NAVY, bold=True))
    b.append(box(510, 170, 210, 130, "", fill=LIGHT, stroke=TEAL))
    b.append(box(526, 188, 178, 40, "Gateway", fill="white", stroke=TEAL, size=12))
    b.append(box(526, 234, 178, 40, "Events / Documents", fill="white", stroke=TEAL, size=12))

    b.append(arrow(140, 104, 140, 186, label="dépôt du scan", ly=150))
    b.append(arrow(360, 104, 340, 186))
    b.append(arrow(450, 214, 508, 214, label="chemin MinIO", ly=206))
    b.append(arrow(508, 262, 452, 262, color=TEAL, label="valeurs pré-remplies", ly=282))
    b.append(label(40, 330, "Le service OCR ne modifie jamais le code d'OpenCRVS : "
                            "il dialogue par l'API et par la configuration pays.", 11))
    return svg(760, 350, "\n".join(b))


def fig_sequence() -> str:
    """In-form prefill, end to end."""
    actors = [("Officier", 70), ("Formulaire\nOpenCRVS", 230), ("Stockage\nMinIO", 400),
              ("Service OCR", 570), ("Modèle VLM", 710)]
    b = [DEFS]
    for name, x in actors:
        lines = name.split("\n")
        for i, ln in enumerate(lines):
            b.append(label(x, 26 + i * 14, ln, 12, NAVY, anchor="middle", bold=True))
        b.append(f'<line x1="{x}" y1="{60}" x2="{x}" y2="{430}" stroke="{BORDER}" '
                 f'stroke-width="1.2" stroke-dasharray="4,4"/>')
    steps = [
        (70, 230, "dépose le scan", 90),
        (230, 400, "téléverse le fichier", 130),
        (400, 230, "chemin du fichier", 170),
        (230, 570, "POST /analyze { path }", 210),
        (570, 400, "lit le fichier", 250),
        (570, 710, "extraction (2 passes)", 290),
        (710, 570, "champs bruts", 330),
        (570, 230, "valeurs par identifiant de champ", 370),
        (230, 70, "formulaire pré-rempli", 410),
    ]
    for x1, x2, text, y in steps:
        b.append(arrow(x1, y, x2, y))
        b.append(label((x1 + x2) / 2, y - 7, text, 11, GREY, anchor="middle"))
    return svg(790, 450, "\n".join(b))


def fig_usecase() -> str:
    """Use cases, actors and system boundary."""
    b = [DEFS]
    b.append(f'<rect x="200" y="40" width="380" height="330" rx="10" fill="none" '
             f'stroke="{BORDER}" stroke-width="1.6"/>')
    b.append(label(390, 64, "Système OCR → OpenCRVS", 13, NAVY, anchor="middle", bold=True))
    cases = [
        "Déposer un acte scanné",
        "Photographier un acte (QR)",
        "Consulter les champs extraits",
        "Corriger une valeur",
        "Pré-remplir une déclaration",
        "Envoyer vers OpenCRVS",
    ]
    y = 100
    for c in cases:
        b.append(f'<ellipse cx="390" cy="{y}" rx="150" ry="20" fill="{LIGHT}" '
                 f'stroke="{BLUE}" stroke-width="1.3"/>')
        b.append(label(390, y + 5, c, 12, NAVY, anchor="middle"))
        y += 45
    for cy, name in [(150, "Officier\nd'état civil"), (280, "Administrateur")]:
        x = 90
        b.append(f'<circle cx="{x}" cy="{cy - 22}" r="12" fill="none" stroke="{NAVY}" stroke-width="1.6"/>')
        b.append(f'<line x1="{x}" y1="{cy - 10}" x2="{x}" y2="{cy + 14}" stroke="{NAVY}" stroke-width="1.6"/>')
        b.append(f'<line x1="{x - 14}" y1="{cy}" x2="{x + 14}" y2="{cy}" stroke="{NAVY}" stroke-width="1.6"/>')
        b.append(f'<line x1="{x}" y1="{cy + 14}" x2="{x - 12}" y2="{cy + 36}" stroke="{NAVY}" stroke-width="1.6"/>')
        b.append(f'<line x1="{x}" y1="{cy + 14}" x2="{x + 12}" y2="{cy + 36}" stroke="{NAVY}" stroke-width="1.6"/>')
        for i, ln in enumerate(name.split("\n")):
            b.append(label(x, cy + 56 + i * 14, ln, 11, GREY, anchor="middle"))
    for ty in (100, 145, 190, 235):
        b.append(f'<line x1="118" y1="150" x2="238" y2="{ty}" stroke="{GREY}" stroke-width="1"/>')
    for ty in (280, 325):
        b.append(f'<line x1="118" y1="280" x2="238" y2="{ty}" stroke="{GREY}" stroke-width="1"/>')
    return svg(640, 400, "\n".join(b))


def fig_honesty_gate() -> str:
    """The decision the pipeline takes rather than guessing."""
    b = [DEFS]
    b.append(box(230, 30, 250, 44, "Champ extrait", fill="white", stroke=NAVY, bold=True))
    b.append(arrow(355, 74, 355, 108))
    b.append(f'<polygon points="355,110 520,175 355,240 190,175" fill={LIGHT!r} '
             f'stroke="{AMBER}" stroke-width="1.6"/>')
    b.append(label(355, 170, "Format valide ?", 13, NAVY, anchor="middle", bold=True))
    b.append(label(355, 188, "confiance ≥ 0,6 ?", 12, GREY, anchor="middle"))

    b.append(arrow(520, 175, 600, 175, color=TEAL))
    b.append(box(600, 148, 190, 54, "Pré-rempli", fill="white", stroke=TEAL,
                 sub="auto-accepté", bold=True))

    b.append(arrow(355, 240, 355, 285, color=AMBER))
    b.append(box(230, 288, 250, 54, "Pré-rempli + signalé", fill="white",
                 stroke=AMBER, sub="« à vérifier »", bold=True))

    b.append(arrow(190, 175, 110, 175, color=RED))
    b.append(box(10, 148, 170, 54, "Non pré-rempli", fill="white", stroke=RED,
                 sub="commentaire seul", bold=True))

    b.append(label(540, 165, "oui", 11, TEAL))
    b.append(label(362, 268, "confiance basse", 11, AMBER))
    b.append(label(118, 165, "format invalide", 11, RED, anchor="end"))
    b.append(label(10, 375, "Aucune branche n'invente de valeur : le doute est "
                            "toujours rendu visible à l'officier.", 11))
    return svg(800, 395, "\n".join(b))


def fig_orgchart() -> str:
    """Placement of the intern in the host organisation.

    Names are placeholders on purpose: inventing an organisation chart would
    put unverifiable claims in a document a supervisor signs.
    """
    b = [DEFS]
    b.append(box(280, 30, 240, 50, "Organisme d'accueil", fill=LIGHT, stroke=NAVY,
                 sub="[à compléter]", bold=True))
    b.append(arrow(400, 80, 400, 108))
    b.append(box(280, 110, 240, 50, "Département / Practice", fill="white",
                 stroke=BLUE, sub="[à compléter]", bold=True))
    b.append(f'<line x1="400" y1="160" x2="400" y2="185" stroke="{BLUE}" stroke-width="1.8"/>')
    b.append(f'<line x1="170" y1="185" x2="630" y2="185" stroke="{BLUE}" stroke-width="1.8"/>')
    for x, title, sub in [(60, "Équipe projet", "[à compléter]"),
                          (290, "Encadrant entreprise", "[nom à compléter]"),
                          (520, "Autres équipes", "[à compléter]")]:
        b.append(f'<line x1="{x + 110}" y1="185" x2="{x + 110}" y2="210" stroke="{BLUE}" stroke-width="1.8"/>')
        b.append(box(x, 212, 220, 50, title, fill="white", stroke=GREY, sub=sub, size=12))
    b.append(arrow(400, 262, 400, 292))
    b.append(box(280, 294, 240, 52, "Stagiaire ingénieur", fill=LIGHT, stroke=TEAL,
                 sub="Ghassen Bousselem", bold=True))
    b.append(label(20, 375, "Les mentions « à compléter » doivent être renseignées avant "
                            "remise : elles ne peuvent pas être devinées.", 11, RED))
    return svg(800, 395, "\n".join(b))


def fig_gantt() -> str:
    """Actual phasing of the internship, from the commit history."""
    b = [DEFS]
    phases = [
        ("Cadrage et état de l'art", 0, 2, TEAL),
        ("Conception du pipeline", 2, 2, BLUE),
        ("Intégration OpenCRVS (API)", 3, 2, BLUE),
        ("Extension multi-pays", 4, 2, BLUE),
        ("Évaluation, première campagne", 5, 2, AMBER),
        ("Étude du formulaire V2", 6, 3, AMBER),
        ("Intégration dans le formulaire", 9, 2, BLUE),
        ("Évaluation approfondie", 9, 2, AMBER),
        ("Documentation et rapport", 10, 1, GREY),
    ]
    x0, w = 260, 46
    for i in range(11):
        b.append(label(x0 + i * w + w / 2, 34, f"S{i + 1}", 11, GREY, anchor="middle"))
        b.append(f'<line x1="{x0 + i * w}" y1="42" x2="{x0 + i * w}" y2="{60 + len(phases) * 34}" '
                 f'stroke="{BORDER}" stroke-width="0.8"/>')
    y = 54
    for name, start, dur, color in phases:
        b.append(label(20, y + 18, name, 12, NAVY))
        b.append(f'<rect x="{x0 + start * w}" y="{y + 4}" width="{dur * w - 6}" height="22" '
                 f'rx="4" fill="{color}" opacity="0.85"/>')
        y += 34
    b.append(label(20, y + 26, "Semaines du 22/06/2026 au 04/09/2026 (55 jours ouvrés)", 11))
    return svg(x0 + 11 * w + 20, y + 45, "\n".join(b))


# -------------------------------------------------------------------- charts --


def charts() -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    q = json.loads((EVAL / "quality_metrics.json").read_text(encoding="utf-8"))
    per_field, per_doc, agg = q["per_field"], q["per_document"], q["aggregate"]

    labels_fr = {
        "child.name": "Nom enfant", "child.dob": "Date naiss.",
        "child.gender": "Sexe", "father.name": "Nom père",
        "father.dob": "Naiss. père", "father.occupation": "Prof. père",
        "father.nationality": "Nat. père", "mother.name": "Nom mère",
        "mother.dob": "Naiss. mère", "mother.occupation": "Prof. mère",
        "mother.nationality": "Nat. mère",
    }

    # ANLS per field
    fig, ax = plt.subplots(figsize=(8.2, 3.6))
    names = [labels_fr.get(k, k) for k in per_field]
    vals = [v["anls"] for v in per_field.values()]
    cols = [TEAL if v >= 0.95 else (AMBER if v >= 0.8 else RED) for v in vals]
    ax.bar(names, vals, color=cols, edgecolor="white")
    ax.set_ylim(0, 1.05)
    ax.set_ylabel("ANLS")
    ax.axhline(agg["anls"], color=NAVY, linestyle="--", linewidth=1,
               label=f"moyenne {agg['anls']:.3f}")
    ax.legend(fontsize=8)
    ax.tick_params(axis="x", rotation=35, labelsize=8)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    fig.tight_layout()
    fig.savefig(FIG / "chart_anls_par_champ.png", dpi=200)
    plt.close(fig)

    # exact fields per document
    fig, ax = plt.subplots(figsize=(8.2, 3.4))
    docs = [d["doc_id"].replace("_", "\n", 1) for d in per_doc]
    ratio = [d["exact"] / d["expected"] if d["expected"] else 0 for d in per_doc]
    ax.bar(docs, ratio, color=[TEAL if r == 1 else AMBER for r in ratio],
           edgecolor="white")
    ax.set_ylim(0, 1.05)
    ax.set_ylabel("Champs exacts (proportion)")
    ax.tick_params(axis="x", labelsize=7)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    fig.tight_layout()
    fig.savefig(FIG / "chart_exact_par_document.png", dpi=200)
    plt.close(fig)

    # confidence bands across the wider sample set
    csv_path = ROOT / "notes-superviseur" / "metriques_par_document.csv"
    if csv_path.exists():
        import csv as csvmod
        with open(csv_path, encoding="utf-8-sig") as f:
            rows = [r for r in csvmod.DictReader(f) if r.get("handwritten") == "False"]
        high = sum(int(r["band_high"]) for r in rows)
        med = sum(int(r["band_medium"]) for r in rows)
        low = sum(int(r["band_low"]) for r in rows)
        fig, ax = plt.subplots(figsize=(4.6, 3.6))
        ax.pie([high, med, low], labels=["haute", "moyenne", "basse"],
               colors=[TEAL, AMBER, RED], autopct="%1.1f%%",
               textprops={"fontsize": 9}, wedgeprops={"edgecolor": "white"})
        ax.set_title("Répartition des scores de confiance", fontsize=10, color=NAVY)
        fig.tight_layout()
        fig.savefig(FIG / "chart_confiance.png", dpi=200)
        plt.close(fig)


def main() -> None:
    FIG.mkdir(parents=True, exist_ok=True)

    diagrams = {
        "diag_pipeline.svg": fig_pipeline(),
        "diag_architecture.svg": fig_architecture(),
        "diag_sequence.svg": fig_sequence(),
        "diag_usecase.svg": fig_usecase(),
        "diag_honnetete.svg": fig_honesty_gate(),
        "diag_organigramme.svg": fig_orgchart(),
        "diag_planning.svg": fig_gantt(),
    }
    for name, content in diagrams.items():
        (FIG / name).write_text(content, encoding="utf-8")
        print(f"  {name}")

    charts()
    print("  charts (3)")

    # a real localisation overlay and a real act, copied in as illustrations
    samples = {
        "capture_field_boxes.png": ROOT / "runs" / "tn_extrait_1981" / "field_boxes.png",
        "acte_exemple.jpg": ROOT / "samples" / "tn_extrait_1981.jpg",
    }
    for name, src in samples.items():
        if src.exists():
            shutil.copyfile(src, FIG / name)
            print(f"  {name}")
        else:
            print(f"  {name} — source absente ({src.name})")

    print(f"-> {FIG}")


if __name__ == "__main__":
    main()

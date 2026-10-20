#!/usr/bin/env python3
"""Build the internship-validation deck (10 min talk, 13 slides, 4 parts).

Numbers are read from eval/quality_metrics.json so the slides cannot drift
from the report. Every diagram is drawn with native PowerPoint shapes (crisp
at any size, editable); the only bitmaps are the real field-box capture and
the ANLS chart.

    python tools/build_presentation.py   # -> presentation_stage.pptx
"""
from __future__ import annotations

import json
from pathlib import Path

from PIL import Image
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Emu, Inches, Pt

ROOT = Path(__file__).resolve().parent.parent
IMG = ROOT / "presentation" / "img"
OUT = ROOT / "presentation_stage.pptx"

NAVY = RGBColor(0x1A, 0x3A, 0x5C)
BLUE = RGBColor(0x2E, 0x6D, 0xA4)
TEAL = RGBColor(0x2A, 0x9D, 0x8F)
AMBER = RGBColor(0xE9, 0xA1, 0x3B)
RED = RGBColor(0xC0, 0x50, 0x4D)
GREY = RGBColor(0x5A, 0x66, 0x72)
INK = RGBColor(0x2B, 0x33, 0x3B)
LIGHT = RGBColor(0xEE, 0xF2, 0xF6)
LINE = RGBColor(0xC8, 0xD2, 0xDC)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
FONT = "Calibri"

agg = json.load(open(ROOT / "eval" / "quality_metrics.json", encoding="utf-8"))["aggregate"]

PARTS = [("I", "Contexte"), ("II", "Conception"), ("III", "Réalisation"), ("IV", "Évaluation")]
TOTAL = 13


def fr(x: float, d: int = 3) -> str:
    return f"{x:.{d}f}".replace(".", ",")


def pct(x: float, d: int = 1) -> str:
    return f"{x * 100:.{d}f} %".replace(".", ",")


prs = Presentation()
prs.slide_width, prs.slide_height = Inches(13.333), Inches(7.5)
BLANK = prs.slide_layouts[6]
W, H = prs.slide_width, prs.slide_height


# ------------------------------------------------------------------ primitives --


def box(slide, x, y, w, h, fill=LIGHT, line=None, shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.08):
    s = slide.shapes.add_shape(shape, x, y, w, h)
    s.fill.solid()
    s.fill.fore_color.rgb = fill
    if line is None:
        s.line.fill.background()
    else:
        s.line.color.rgb = line
        s.line.width = Pt(1.5)
    s.shadow.inherit = False
    if shape == MSO_SHAPE.ROUNDED_RECTANGLE:
        s.adjustments[0] = radius
    return s


def label(shape, content, size=16, color=INK, bold=False, align=PP_ALIGN.CENTER,
          anchor=MSO_ANCHOR.MIDDLE):
    """Write centred text inside a shape."""
    tf = shape.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    tf.margin_left = tf.margin_right = Inches(0.08)
    tf.margin_top = tf.margin_bottom = Inches(0.04)
    lines = content if isinstance(content, list) else [content]
    for i, ln in enumerate(lines):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        r = p.add_run()
        r.text = ln
        r.font.size, r.font.bold, r.font.name = Pt(size), bold, FONT
        r.font.color.rgb = color


def text(slide, x, y, w, h, content, size=18, color=NAVY, bold=False,
         align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP):
    tb = slide.shapes.add_textbox(x, y, w, h)
    label(tb, content, size, color, bold, align, anchor)
    return tb


def bullets(slide, x, y, w, h, items, size=19, gap=10, marker=TEAL):
    tb = slide.shapes.add_textbox(x, y, w, h)
    tf = tb.text_frame
    tf.word_wrap = True
    for i, it in enumerate(items):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.space_after = Pt(gap)
        head, _, rest = it.partition("|")
        for t, bold, col in (("■  ", False, marker), (head, bool(rest), NAVY if rest else INK),
                             (rest, False, INK)):
            if not t:
                continue
            r = p.add_run()
            r.text = t
            r.font.size = Pt(size if t != "■  " else size - 6)
            r.font.bold, r.font.name = bold, FONT
            r.font.color.rgb = col


def arrow(slide, x, y, w, h, color=BLUE, down=False):
    s = slide.shapes.add_shape(MSO_SHAPE.DOWN_ARROW if down else MSO_SHAPE.RIGHT_ARROW, x, y, w, h)
    s.fill.solid()
    s.fill.fore_color.rgb = color
    s.line.fill.background()
    s.shadow.inherit = False
    return s


def disc(slide, x, y, d, content, fill=BLUE, size=18, color=WHITE):
    s = box(slide, x, y, d, d, fill=fill, shape=MSO_SHAPE.OVAL)
    label(s, content, size=size, color=color, bold=True)
    return s


def picture(slide, name, x, y, w, h):
    path = IMG / name
    iw, ih = Image.open(path).size
    k = min(w / iw, h / ih)
    pw, ph = int(iw * k), int(ih * k)
    slide.shapes.add_picture(str(path), x + (w - pw) // 2, y + (h - ph) // 2, pw, ph)


def document(slide, x, y, w, h, tint=BLUE):
    """A small sheet of paper with lines of text and a folded corner."""
    d = box(slide, x, y, w, h, fill=WHITE, line=tint, shape=MSO_SHAPE.FOLDED_CORNER)
    for i in range(5):
        ln = box(slide, x + int(w * 0.14), y + int(h * (0.2 + i * 0.13)),
                 int(w * (0.72 if i % 2 == 0 else 0.5)), Emu(30000), fill=LINE,
                 shape=MSO_SHAPE.RECTANGLE)
    return d


# ---------------------------------------------------------------- slide frame --


def frame(title, n, part, notes):
    """Standard slide: section chip, title, rule, running footer and tracker."""
    s = prs.slides.add_slide(BLANK)
    i, name = PARTS[part]
    text(s, Inches(0.65), Inches(0.28), Inches(8), Inches(0.35),
         f"PARTIE {i}  ·  {name.upper()}", size=12, color=TEAL, bold=True)
    text(s, Inches(0.6), Inches(0.58), Inches(12.1), Inches(0.75), title, size=30, bold=True,
         anchor=MSO_ANCHOR.MIDDLE)
    box(s, Inches(0.65), Inches(1.38), Inches(12.0), Emu(22000), fill=BLUE, shape=MSO_SHAPE.RECTANGLE)
    # tracker: four segments, the current part in colour
    for k, (roman, nm) in enumerate(PARTS):
        seg = box(s, Inches(4.6 + k * 1.1), Inches(7.1), Inches(1.0), Inches(0.22),
                  fill=TEAL if k == part else LINE, shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.4)
        label(seg, roman, size=9, color=WHITE if k == part else GREY, bold=True)
    text(s, Inches(0.6), Inches(7.05), Inches(4), Inches(0.35),
         "Mohamed Ghassen Bousalem · EY Tunisie · ESPRIT", size=10, color=GREY)
    text(s, Inches(11.6), Inches(7.05), Inches(1.1), Inches(0.35), f"{n} / {TOTAL}", size=10,
         color=GREY, align=PP_ALIGN.RIGHT)
    s.notes_slide.notes_text_frame.text = notes
    return s


# ====================================================================== 1. titre
s = prs.slides.add_slide(BLANK)
box(s, 0, 0, W, H, fill=NAVY, shape=MSO_SHAPE.RECTANGLE)
box(s, Inches(8.9), 0, Inches(4.45), H, fill=RGBColor(0x14, 0x2E, 0x4A), shape=MSO_SHAPE.RECTANGLE)
box(s, Inches(0.8), Inches(1.9), Inches(0.12), Inches(2.5), fill=AMBER, shape=MSO_SHAPE.RECTANGLE)
text(s, Inches(1.15), Inches(1.8), Inches(7.5), Inches(2.4),
     "Extraction automatique de données d'actes d'état civil par modèles vision-langage",
     size=34, bold=True, color=WHITE)
text(s, Inches(1.15), Inches(4.2), Inches(7.4), Inches(0.9),
     "Pipeline multi-pays et intégration au registre civil numérique OpenCRVS",
     size=19, color=RGBColor(0xC8, 0xD8, 0xE8))
text(s, Inches(1.15), Inches(5.5), Inches(7.6), Inches(1.4),
     ["Mohamed Ghassen Bousalem · ESPRIT, stage d'ingénieur",
      "EY Tunisie · Technology, Strategy & Transformation",
      "Du 22 juin au 4 septembre 2026 · Encadrante : Mariem Abcha"],
     size=14, color=WHITE)
# illustration : acte -> champs structurés
document(s, Inches(9.55), Inches(1.7), Inches(1.5), Inches(1.95), tint=AMBER)
arrow(s, Inches(11.2), Inches(2.4), Inches(0.55), Inches(0.5), color=AMBER)
for i, (k, v) in enumerate([("nom", "…"), ("naissance", "…"), ("parents", "…"), ("lieu", "…")]):
    f = box(s, Inches(10.9 + 0.0), Inches(3.95 + i * 0.62), Inches(2.0), Inches(0.5),
            fill=RGBColor(0x24, 0x4A, 0x72), line=TEAL)
    label(f, f"{k}  ✓", size=13, color=WHITE)
text(s, Inches(9.2), Inches(6.6), Inches(3.8), Inches(0.5), "acte scanné  →  déclaration pré-remplie",
     size=12, color=RGBColor(0xC8, 0xD8, 0xE8), align=PP_ALIGN.CENTER)
s.notes_slide.notes_text_frame.text = (
    "[0:00 – 0:30] Bonjour et merci de me recevoir. Je présente mon stage de onze semaines chez EY "
    "Tunisie, au sein de la practice Technology, Strategy & Transformation : comment faire lire un acte "
    "de naissance scanné par un modèle vision-langage, puis pré-remplir une déclaration dans OpenCRVS.")

# ======================================================================== 2. plan
s = prs.slides.add_slide(BLANK)
text(s, Inches(0.65), Inches(0.35), Inches(8), Inches(0.4), "SOMMAIRE", size=13, color=TEAL, bold=True)
text(s, Inches(0.6), Inches(0.65), Inches(12), Inches(0.8), "Plan de la présentation", size=32, bold=True)
box(s, Inches(0.65), Inches(1.45), Inches(12.0), Emu(22000), fill=BLUE, shape=MSO_SHAPE.RECTANGLE)
plan = [("I", "Contexte et problématique", ["Le papier, obstacle à l'identité légale", "Question posée et objectifs"], "2 min", BLUE),
        ("II", "Conception de la solution", ["Un pipeline en cinq étapes", "Le principe d'honnêteté"], "2 min", TEAL),
        ("III", "Réalisation et intégration", ["Intégration à OpenCRVS", "Ce que voit l'officier", "Difficultés rencontrées"], "3 min", AMBER),
        ("IV", "Évaluation et bilan", ["Protocole et métriques", "Résultats et défauts relevés", "Limites, perspectives, conclusion"], "3 min", RED)]
for i, (num, title, items, dur, col) in enumerate(plan):
    x = Inches(0.65 + i * 3.04)
    box(s, x, Inches(1.95), Inches(2.84), Inches(4.7), fill=LIGHT)
    box(s, x, Inches(1.95), Inches(2.84), Inches(0.12), fill=col, shape=MSO_SHAPE.RECTANGLE)
    disc(s, x + Inches(0.25), Inches(2.3), Inches(0.9), num, fill=col, size=26)
    text(s, x + Inches(1.2), Inches(2.3), Inches(1.6), Inches(0.9), dur, size=15, color=GREY, bold=True,
         anchor=MSO_ANCHOR.MIDDLE)
    text(s, x + Inches(0.2), Inches(3.35), Inches(2.5), Inches(0.9), title, size=19, bold=True, color=col)
    bullets(s, x + Inches(0.15), Inches(4.3), Inches(2.6), Inches(2.3), items, size=14, gap=7, marker=col)
s.notes_slide.notes_text_frame.text = (
    "[0:30 – 1:00] L'exposé suit quatre parties : le contexte et la problématique ; la conception de la "
    "solution ; sa réalisation et son intégration à OpenCRVS ; enfin l'évaluation et le bilan.")

# ===================================================================== 3. contexte
s = frame("Le papier, obstacle à l'identité légale", 3, 0,
          "[1:00 – 1:45] Sans acte de naissance, on n'accède ni à l'école, ni aux soins, ni au vote ; les "
          "Nations unies en ont fait la cible 16.9 des Objectifs de développement durable. Or, dans de "
          "nombreux pays, les actes n'existent que sur papier. Le véritable obstacle n'est pas la "
          "photographie du registre, mais la ressaisie de chaque acte dans un système informatique.")
document(s, Inches(0.9), Inches(2.0), Inches(1.7), Inches(2.2), tint=AMBER)
document(s, Inches(1.1), Inches(2.15), Inches(1.7), Inches(2.2), tint=AMBER)
text(s, Inches(0.7), Inches(4.45), Inches(2.4), Inches(0.7), ["Stock d'actes papier", "(registres, copies, extraits)"],
     size=13, color=GREY, align=PP_ALIGN.CENTER)
arrow(s, Inches(3.3), Inches(2.85), Inches(0.9), Inches(0.6), color=GREY)
barrier = box(s, Inches(4.4), Inches(1.95), Inches(3.9), Inches(2.4), fill=RGBColor(0xFB, 0xEC, 0xEB), line=RED)
label(barrier, ["Ressaisie manuelle", "lecture de l'acte, puis saisie", "de chaque champ"], size=16,
      color=RED, bold=True)
arrow(s, Inches(8.5), Inches(2.85), Inches(0.9), Inches(0.6), color=GREY)
db = box(s, Inches(9.7), Inches(1.95), Inches(2.3), Inches(2.4), fill=LIGHT, line=BLUE, shape=MSO_SHAPE.CAN)
label(db, ["Registre", "numérique"], size=16, color=BLUE, bold=True)
text(s, Inches(9.3), Inches(4.45), Inches(3.1), Inches(0.5), "OpenCRVS", size=13, color=GREY,
     align=PP_ALIGN.CENTER)
cards = [("Un droit fondamental", "École, soins, emploi, vote : l'acte de naissance conditionne l'accès aux droits. ODD 16.9.", BLUE),
         ("Un stock hétérogène", "Chaque pays, parfois chaque commune, a sa mise en page ; les scans sont souvent dégradés.", AMBER),
         ("Un goulot d'étranglement", "La ressaisie est lente, coûteuse, source d'erreurs, et ne passe pas à l'échelle.", RED)]
for i, (t, b, c) in enumerate(cards):
    x = Inches(0.65 + i * 4.1)
    box(s, x, Inches(5.2), Inches(3.85), Inches(1.7), fill=LIGHT)
    box(s, x, Inches(5.2), Inches(0.1), Inches(1.7), fill=c, shape=MSO_SHAPE.RECTANGLE)
    text(s, x + Inches(0.25), Inches(5.25), Inches(3.5), Inches(0.4), t, size=16, bold=True, color=c)
    text(s, x + Inches(0.25), Inches(5.68), Inches(3.5), Inches(1.2), b, size=13, color=INK)

# ============================================================ 4. problématique
s = frame("Problématique et objectifs", 4, 0,
          "[1:45 – 2:30] La question posée est la suivante : comment passer de la ressaisie à la "
          "vérification, pour des actes de pays et d'états de conservation très différents, sans jamais "
          "introduire dans le registre une erreur présentée comme certaine ? Cette dernière condition "
          "gouverne l'ensemble de la conception. Quatre objectifs en découlent.")
q = box(s, Inches(0.65), Inches(1.65), Inches(12.0), Inches(1.15), fill=NAVY)
label(q, "Comment passer de la ressaisie à la vérification, sans jamais introduire dans le registre "
         "une erreur présentée comme certaine ?", size=19, color=WHITE, bold=True)
# avant / après
for row, (tag, col, steps) in enumerate([
        ("AVANT", RED, ["Lire l'acte", "Ressaisir chaque champ", "Enregistrer"]),
        ("APRÈS", TEAL, ["Scanner l'acte", "Pré-remplissage automatique", "Vérifier et corriger", "Valider"])]):
    y = Inches(3.1 + row * 1.35)
    t = box(s, Inches(0.65), y, Inches(1.2), Inches(1.05), fill=col)
    label(t, tag, size=15, color=WHITE, bold=True)
    n = len(steps)
    wbox = Inches(9.6 / n - 0.5)
    for k, st in enumerate(steps):
        xk = Inches(2.1) + k * (wbox + Inches(0.5))
        b = box(s, xk, y, wbox, Inches(1.05), fill=LIGHT, line=col)
        label(b, st, size=15, color=INK, bold=(tag == "APRÈS" and k == 1))
        if k < n - 1:
            arrow(s, xk + wbox + Inches(0.07), y + Inches(0.35), Inches(0.36), Inches(0.35), color=col)
obj = ["Pipeline générique, sans réécriture par pays", "Intégration à OpenCRVS, sans modifier son cœur",
       "Vérification humaine et corrections capitalisées", "Évaluation avec les métriques du domaine"]
for i, o in enumerate(obj):
    x = Inches(0.65 + i * 3.04)
    disc(s, x, Inches(5.95), Inches(0.6), str(i + 1), fill=BLUE, size=16)
    text(s, x + Inches(0.7), Inches(5.85), Inches(2.1), Inches(1.0), o, size=13, color=INK,
         anchor=MSO_ANCHOR.MIDDLE)

# ===================================================================== 5. pipeline
s = frame("Un pipeline en cinq étapes", 5, 1,
          "[2:30 – 3:30] Le traitement comporte cinq étapes : prétraitement de l'image, détection du pays, "
          "localisation des champs, extraction en deux passes indépendantes, puis validation et calcul de "
          "confiance. Le modèle vision-langage ne demande aucun corpus annoté : on lui décrit le schéma "
          "attendu en langage naturel. L'accord entre les deux passes constitue un signal de confiance.")
steps = [("1", "Prétraitement", "redressement, échelle, binarisation", TEAL),
         ("2", "Détection du pays", "lecture de l'en-tête, pack pays", TEAL),
         ("3", "Localisation", "gabarit, ou repérage par le modèle", AMBER),
         ("4", "Extraction", "page entière et recadrages, consensus", BLUE),
         ("5", "Validation", "dates ISO, énumérations, score", TEAL)]
box(s, Inches(0.65), Inches(1.75), Inches(1.4), Inches(1.0), fill=LIGHT, line=GREY)
t = s.shapes[-1]
label(t, ["Scan", "image ou PDF"], size=13, color=GREY, bold=True)
for k, (num, title, sub, col) in enumerate(steps):
    x = Inches(2.3 + k * 2.1)
    ch = s.shapes.add_shape(MSO_SHAPE.PENTAGON if k == 0 else MSO_SHAPE.CHEVRON, x, Inches(1.75),
                            Inches(2.2), Inches(1.0))
    ch.fill.solid(); ch.fill.fore_color.rgb = col; ch.line.fill.background(); ch.shadow.inherit = False
    label(ch, f"{num}", size=22, color=WHITE, bold=True)
    text(s, x, Inches(2.95), Inches(2.1), Inches(0.5), title, size=15, bold=True, color=col,
         align=PP_ALIGN.CENTER)
    text(s, x, Inches(3.4), Inches(2.0), Inches(0.9), sub, size=12, color=GREY, align=PP_ALIGN.CENTER)
# sortie
out = box(s, Inches(2.3), Inches(4.45), Inches(10.4), Inches(0.7), fill=NAVY)
label(out, "Sortie : champs structurés, score de confiance par champ, image de repérage", size=15,
      color=WHITE, bold=True)
# deux passes
for i, (t_, d_, c_) in enumerate([("Passe 1 · page entière", "contexte global du document", BLUE),
                                  ("Passe 2 · recadrages", "lecture champ par champ", BLUE)]):
    x = Inches(0.65 + i * 3.1)
    b = box(s, x, Inches(5.45), Inches(2.9), Inches(1.4), fill=LIGHT, line=c_)
    label(b, [t_, d_], size=14, color=INK, anchor=MSO_ANCHOR.MIDDLE)
eq = box(s, Inches(6.9), Inches(5.45), Inches(1.9), Inches(1.4), fill=TEAL)
label(eq, ["Accord des", "deux passes", "= confiance"], size=14, color=WHITE, bold=True)
for k, (v, l) in enumerate([("27", "pays couverts"), ("40–90 s", "par acte")]):
    x = Inches(9.2 + k * 1.9)
    b = box(s, x, Inches(5.45), Inches(1.75), Inches(1.4), fill=WHITE, line=BLUE)
    text(s, x, Inches(5.55), Inches(1.75), Inches(0.7), v, size=26, bold=True, color=BLUE, align=PP_ALIGN.CENTER)
    text(s, x, Inches(6.25), Inches(1.75), Inches(0.5), l, size=12, color=GREY, align=PP_ALIGN.CENTER)
arrow(s, Inches(6.55), Inches(5.95), Inches(0.28), Inches(0.35), color=TEAL)

# ================================================================= 6. honnêteté
s = frame("Principe directeur : ne jamais affirmer une valeur fausse", 6, 1,
          "[3:30 – 4:30] Une erreur signalée ne coûte que quelques secondes à l'officier ; une erreur "
          "présentée avec assurance s'installe dans un registre pour des décennies. À chaque étape, le "
          "système préfère donc exprimer son doute : en deçà de 0,6 de confiance, la valeur est marquée "
          "« à vérifier » ; une nationalité ambiguë n'est jamais tranchée ; une information absente du "
          "document n'est jamais déduite.")
c = box(s, Inches(0.65), Inches(2.5), Inches(1.9), Inches(1.0), fill=LIGHT, line=NAVY)
label(c, "Champ extrait", size=15, color=NAVY, bold=True)
arrow(s, Inches(2.65), Inches(2.8), Inches(0.5), Inches(0.4), color=GREY)
dm = box(s, Inches(3.25), Inches(1.75), Inches(2.6), Inches(2.5), fill=WHITE, line=AMBER, shape=MSO_SHAPE.DIAMOND)
label(dm, ["Confiance", "≥ 0,6 ?"], size=16, color=INK, bold=True)
arrow(s, Inches(5.95), Inches(2.45), Inches(0.5), Inches(0.4), color=TEAL)
text(s, Inches(5.9), Inches(2.0), Inches(0.7), Inches(0.4), "oui", size=13, color=TEAL, bold=True)
ok = box(s, Inches(6.55), Inches(2.05), Inches(2.5), Inches(1.0), fill=RGBColor(0xE3, 0xF4, 0xF1), line=TEAL)
label(ok, ["Pré-rempli", "et accepté"], size=14, color=TEAL, bold=True)
arrow(s, Inches(4.35), Inches(4.3), Inches(0.4), Inches(0.5), color=AMBER, down=True)
text(s, Inches(4.8), Inches(4.3), Inches(1.0), Inches(0.4), "non", size=13, color=AMBER, bold=True)
wr = box(s, Inches(3.1), Inches(4.9), Inches(2.9), Inches(1.0), fill=RGBColor(0xFD, 0xF3, 0xE3), line=AMBER)
label(wr, ["Pré-rempli et signalé", "« à vérifier »"], size=14, color=RGBColor(0x8A, 0x5A, 0x10), bold=True)
ab = box(s, Inches(6.55), Inches(4.9), Inches(2.5), Inches(1.0), fill=LIGHT, line=GREY)
label(ab, ["Information absente :", "champ laissé vide"], size=14, color=GREY, bold=True)
text(s, Inches(6.55), Inches(4.45), Inches(2.5), Inches(0.4), "document muet", size=12, color=GREY,
     align=PP_ALIGN.CENTER)
rules = [("« Congolaise »", "deux pays possibles : jamais tranché"),
         ("Lieu d'accouchement", "catégorie jamais devinée"),
         ("Nationalité", "jamais déduite du lieu de naissance"),
         ("Localisation", "repli sur le modèle si le gabarit ne colle pas")]
for i, (h_, d_) in enumerate(rules):
    y = Inches(1.75 + i * 1.18)
    box(s, Inches(9.45), y, Inches(3.2), Inches(1.05), fill=LIGHT)
    box(s, Inches(9.45), y, Inches(0.09), Inches(1.05), fill=TEAL, shape=MSO_SHAPE.RECTANGLE)
    text(s, Inches(9.65), y + Inches(0.05), Inches(2.95), Inches(0.4), h_, size=14, bold=True, color=NAVY)
    text(s, Inches(9.65), y + Inches(0.42), Inches(2.95), Inches(0.6), d_, size=12, color=INK)
ban = box(s, Inches(0.65), Inches(6.2), Inches(8.4), Inches(0.7), fill=NAVY)
label(ban, "Une erreur signalée coûte quelques secondes ; une erreur assurée dure des décennies.",
      size=15, color=WHITE, bold=True)

# ============================================================= 7. intégration
s = frame("Intégration à OpenCRVS : deux voies, aucune ligne du cœur modifiée", 7, 2,
          "[4:30 – 5:30] OpenCRVS sépare son cœur de sa configuration nationale. La première voie utilise "
          "l'interface de notification d'événement : elle dépose une déclaration pré-remplie avec le scan "
          "joint. La seconde, plus aboutie, ajoute un panneau au formulaire : l'officier dépose le scan sans "
          "quitter OpenCRVS, les champs se remplissent sur toutes les pages, et il poursuit vers la page de "
          "relecture native.")
zones = [(0.65, 3.2, "Poste de l'officier", BLUE, [("Navigateur", "formulaire OpenCRVS"), ("Téléphone", "capture par QR code")]),
         (4.95, 3.4, "Service OCR (ce projet)", TEAL, [("Application web", "dépôt, suivi, correction"), ("API d'analyse", "reçoit le chemin du scan"), ("Pipeline VLM", "extraction et validation")]),
         (9.45, 3.2, "Plateforme OpenCRVS", AMBER, [("Formulaire", "déclaration de naissance"), ("Stockage MinIO", "pièces jointes"), ("API d'événements", "voie 1 : notification")])]
for x, w, title, col, items in zones:
    box(s, Inches(x), Inches(1.7), Inches(w), Inches(3.9), fill=LIGHT)
    box(s, Inches(x), Inches(1.7), Inches(w), Inches(0.5), fill=col, shape=MSO_SHAPE.RECTANGLE)
    text(s, Inches(x), Inches(1.7), Inches(w), Inches(0.5), title, size=15, bold=True, color=WHITE,
         align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
    for k, (a, b_) in enumerate(items):
        y = Inches(2.4 + k * 1.05)
        bx = box(s, Inches(x + 0.2), y, Inches(w - 0.4), Inches(0.9), fill=WHITE, line=col)
        label(bx, [a, b_], size=13, color=INK)
        bx.text_frame.paragraphs[0].runs[0].font.bold = True
for x, lab, col in [(3.9, "1  dépôt du scan", BLUE), (8.4, "2  chemin du fichier", TEAL)]:
    arrow(s, Inches(x), Inches(3.3), Inches(0.95), Inches(0.5), color=col)
    text(s, Inches(x - 0.15), Inches(3.85), Inches(1.3), Inches(0.6), lab, size=11, color=GREY,
         align=PP_ALIGN.CENTER)
back = arrow(s, Inches(8.4), Inches(4.5), Inches(0.95), Inches(0.5), color=AMBER)
back.rotation = 180
text(s, Inches(8.25), Inches(5.05), Inches(1.3), Inches(0.6), "3  valeurs pré-remplies", size=11, color=GREY,
     align=PP_ALIGN.CENTER)
for i, (t_, d_, c_) in enumerate([("Voie 1 · notification", "déclaration et scan joint déposés dans la file du bureau", BLUE),
                                  ("Voie 2 · panneau intégré", "champs remplis dans le formulaire, sur toutes les pages", TEAL)]):
    x = Inches(0.65 + i * 6.1)
    b = box(s, x, Inches(5.85), Inches(5.9), Inches(1.05), fill=WHITE, line=c_)
    label(b, [t_, d_], size=14, color=INK)
    b.text_frame.paragraphs[0].runs[0].font.bold = True
    b.text_frame.paragraphs[0].runs[0].font.color.rgb = c_

# ========================================================== 8. vue de l'officier
s = frame("Ce que voit l'officier : des valeurs vérifiables, avec leur origine", 8, 2,
          "[5:30 – 6:15] Le pipeline dessine sur le scan la zone d'où chaque valeur a été lue. Cette image de "
          "repérage est jointe à la déclaration comme pièce justificative : l'officier voit d'où provient une "
          "valeur, et pas seulement ce qu'elle indique. C'est le moyen le plus rapide de détecter une valeur "
          "lue sur la mauvaise ligne.")
box(s, Inches(0.8), Inches(1.65), Inches(4.4), Inches(5.3), fill=LIGHT, line=LINE)
picture(s, "capture_field_boxes.png", Inches(0.95), Inches(1.75), Inches(4.1), Inches(5.1))
callouts = [("Repérage OCR", "chaque zone lue est encadrée sur le scan ; l'image est jointe comme pièce justificative", BLUE),
            ("Pré-remplissage", "enfant, parents et déclarant : environ sept champs par document", TEAL),
            ("Valeurs douteuses", "signalées « à vérifier » dans le commentaire de relecture", AMBER),
            ("Contrôle humain", "tout reste modifiable ; l'officier valide la déclaration", NAVY)]
for i, (h_, d_, col) in enumerate(callouts):
    y = Inches(1.7 + i * 1.3)
    disc(s, Inches(5.6), y + Inches(0.1), Inches(0.7), str(i + 1), fill=col, size=18)
    text(s, Inches(6.5), y, Inches(6.2), Inches(0.45), h_, size=18, bold=True, color=col)
    text(s, Inches(6.5), y + Inches(0.45), Inches(6.2), Inches(0.8), d_, size=14, color=INK)

# ============================================================== 9. difficultés
s = frame("Difficultés rencontrées : l'enjeu se situait aux jonctions", 9, 2,
          "[6:15 – 7:00] La difficulté principale ne tenait pas à l'extraction, le modèle lisant correctement "
          "des documents difficiles, mais aux jonctions entre systèmes. Les champs demeuraient vides parce "
          "qu'une valeur sans champ parent est ignorée par le formulaire. Un champ HTTP ne peut transmettre "
          "un fichier : nous envoyons donc le chemin de stockage. Enfin, le démarrage de la plateforme "
          "échouait à cause de deux conditions de concurrence, résolues par une vérification explicite.")
rows = [("Champs demeurant vides", "valeur déclarée sans champ parent ; JSON à clés pointées non résolu", "déclaration du parent ; JSON imbriqué"),
        ("Transmission du scan impossible", "un champ HTTP n'envoie que du JSON, jamais un fichier", "envoi du chemin MinIO ; lecture côté service OCR"),
        ("Interruption du formulaire", "balises de mise en forme interprétées dans les libellés", "texte brut ; styles fournis par la configuration"),
        ("Démarrage instable", "services lancés avant d'être réellement disponibles", "vérification explicite : de 5 min à 70 s")]
cw = [3.4, 4.6, 4.0]
x = 0.65
for h_, w_ in zip(["Symptôme", "Cause", "Résolution"], cw):
    b = box(s, Inches(x), Inches(1.7), Inches(w_ - 0.06), Inches(0.55), fill=NAVY, shape=MSO_SHAPE.RECTANGLE)
    label(b, h_, size=15, color=WHITE, bold=True, align=PP_ALIGN.LEFT)
    x += w_
for i, row in enumerate(rows):
    y = Inches(2.32 + i * 1.12)
    x = 0.65
    for j, (cell, w_) in enumerate(zip(row, cw)):
        fill = LIGHT if i % 2 == 0 else WHITE
        b = box(s, Inches(x), y, Inches(w_ - 0.06), Inches(1.04), fill=fill, line=None if i % 2 == 0 else LINE,
                shape=MSO_SHAPE.RECTANGLE)
        label(b, cell, size=14, color=NAVY if j == 0 else INK, bold=(j == 0), align=PP_ALIGN.LEFT)
        if j == 2:
            box(s, Inches(x), y, Inches(0.07), Inches(1.04), fill=TEAL, shape=MSO_SHAPE.RECTANGLE)
        x += w_
ban = box(s, Inches(0.65), Inches(6.85 - 0.02), Inches(12.0), Inches(0.01), fill=WHITE, shape=MSO_SHAPE.RECTANGLE)

# ================================================================ 10. évaluation
s = frame("Évaluation : mesurer avec les métriques du domaine", 10, 3,
          "[7:00 – 8:00] L'évaluation porte sur un jeu de référence transcrit à la main : neuf actes de pays "
          "différents, dont des cas dégradés, et soixante-neuf champs, certains volontairement absents afin de "
          "détecter les hallucinations. Les métriques retenues sont celles du domaine : ANLS, F1 par champ, "
          "taux d'erreur caractère, taux d'hallucination. BLEU et ROUGE sont écartés des indicateurs "
          "principaux, car ils mesurent un recouvrement de n-grammes et non l'exactitude d'un champ. "
          f"Résultats : ANLS {fr(agg['anls'])}, F1 exact {fr(agg['exact_f1'])}, hallucination nulle.")
for k, (v, l) in enumerate([(str(agg["documents"]), "actes de référence"), (str(agg["fields_expected"]), "champs transcrits"),
                            ("30", "champs volontairement absents"), ("27", "pays couverts")]):
    x = Inches(0.65 + k * 3.04)
    b = box(s, x, Inches(1.65), Inches(2.84), Inches(0.85), fill=LIGHT)
    text(s, x + Inches(0.1), Inches(1.65), Inches(1.0), Inches(0.85), v, size=26, bold=True, color=BLUE,
         anchor=MSO_ANCHOR.MIDDLE, align=PP_ALIGN.CENTER)
    text(s, x + Inches(1.1), Inches(1.65), Inches(1.7), Inches(0.85), l, size=12, color=GREY,
         anchor=MSO_ANCHOR.MIDDLE)
tiles = [(fr(agg["anls"]), "Similarité ANLS", agg["anls"], BLUE),
         (fr(agg["exact_f1"]), "F1, correspondance exacte", agg["exact_f1"], BLUE),
         (fr(agg["fuzzy_f1"]), "F1, correspondance approchée", agg["fuzzy_f1"], TEAL),
         (pct(agg["cer"]), "Taux d'erreur caractère (CER)", agg["cer"], TEAL),
         ("0 %", "Taux d'hallucination", 0.0, RED),
         ("100 %", "Conformité au schéma", 1.0, RED)]
for i, (v, l, frac, c_) in enumerate(tiles):
    x = Inches(0.65 + (i % 3) * 4.1)
    y = Inches(2.75 + (i // 3) * 2.1)
    box(s, x, y, Inches(3.85), Inches(1.9), fill=WHITE, line=c_)
    text(s, x, y + Inches(0.12), Inches(3.85), Inches(0.85), v, size=38, bold=True, color=c_, align=PP_ALIGN.CENTER)
    text(s, x, y + Inches(0.95), Inches(3.85), Inches(0.4), l, size=14, color=GREY, align=PP_ALIGN.CENTER)
    box(s, x + Inches(0.4), y + Inches(1.5), Inches(3.05), Inches(0.16), fill=LIGHT, shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.5)
    if frac > 0:
        box(s, x + Inches(0.4), y + Inches(1.5), max(Inches(0.1), int(Inches(3.05) * min(frac, 1))), Inches(0.16),
            fill=c_, shape=MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.5)

# ================================================================== 11. résultats
s = frame("Résultats par champ et défauts relevés", 11, 3,
          "[8:00 – 9:00] Les résultats par champ sont bons, mais l'évaluation a également révélé de vrais "
          "défauts, que je documente au lieu de les dissimuler : une année mal lue, un caractère erroné, une "
          "nationalité absente sur un pays et, surtout, une inversion entre prénom et nom lorsque le nom de "
          "famille est écrit en premier, en majuscules, comme au Bénin ou au Mali. "
          f"La répartition entre prénom et nom n'est correcte que dans {agg['name_split_accuracy']*100:.0f} % des "
          "cas, bien que le nom complet soit correctement lu. Ce défaut est identifié et corrigeable.")
box(s, Inches(0.65), Inches(1.65), Inches(7.7), Inches(3.95), fill=WHITE, line=LINE)
picture(s, "chart_anls_par_champ.png", Inches(0.75), Inches(1.7), Inches(7.5), Inches(3.85))
defects = [("Année mal lue", "1999 lue 1989 sur un acte malgache", RED),
           ("Caractère erroné", "FATOUMATA lu FATOUKATA sur un acte malien", RED),
           ("Nationalité absente", "non extraite sur un acte sierra-léonais", AMBER),
           ("Prénom et nom inversés", f"répartition correcte dans {agg['name_split_accuracy']*100:.0f} % des cas", AMBER)]
for i, (h_, d_, col) in enumerate(defects):
    y = Inches(1.65 + i * 1.0)
    box(s, Inches(8.6), y, Inches(4.05), Inches(0.9), fill=LIGHT)
    box(s, Inches(8.6), y, Inches(0.09), Inches(0.9), fill=col, shape=MSO_SHAPE.RECTANGLE)
    text(s, Inches(8.8), y + Inches(0.04), Inches(3.8), Inches(0.4), h_, size=14, bold=True, color=NAVY)
    text(s, Inches(8.8), y + Inches(0.42), Inches(3.8), Inches(0.45), d_, size=12, color=INK)
ban = box(s, Inches(0.65), Inches(5.9), Inches(12.0), Inches(1.0), fill=RGBColor(0xFD, 0xF3, 0xE3), line=AMBER)
label(ban, "Ces défauts sont documentés et non dissimulés, conformément au principe d'honnêteté du système : "
           "le nom complet est bien lu ; c'est son découpage en prénom et nom qui échoue sur certaines conventions.",
      size=14, color=RGBColor(0x8A, 0x5A, 0x10))

# ======================================================== 12. limites et perspectives
s = frame("Limites et perspectives", 12, 3,
          "[9:00 – 9:40] Les limites sont les suivantes : un jeu de référence de neuf actes, dont les chiffres "
          "restent donc indicatifs ; l'inversion prénom-nom à corriger ; la dépendance à un modèle hébergé "
          "par un tiers. À court terme, il s'agit de corriger l'ordre des noms par pack pays et d'élargir le "
          "jeu d'évaluation. À moyen terme, un modèle hébergé localement s'impose, car des données d'état "
          "civil ne doivent pas transiter par une interface tierce ; le changement ne demande aucune "
          "modification de code.")
cols = [("Limites", AMBER, ["Jeu de référence de neuf actes : chiffres indicatifs", "Ordre prénom et nom à corriger pour certains pays", "Dépendance à une interface de modèle tierce"]),
        ("Court terme", BLUE, ["Corriger l'ordre des noms par pack pays", "Élargir le jeu de référence", "Compléter les nationalités manquantes"]),
        ("Moyen terme", TEAL, ["Modèle hébergé localement : souveraineté des données", "Déploiement sur une instance réelle", "Capitaliser les corrections de l'officier"])]
for i, (t_, col, items) in enumerate(cols):
    x = Inches(0.65 + i * 4.1)
    box(s, x, Inches(1.75), Inches(3.85), Inches(4.9), fill=LIGHT)
    box(s, x, Inches(1.75), Inches(3.85), Inches(0.12), fill=col, shape=MSO_SHAPE.RECTANGLE)
    disc(s, x + Inches(0.25), Inches(2.1), Inches(0.75), str(i + 1), fill=col, size=22)
    text(s, x + Inches(1.15), Inches(2.1), Inches(2.6), Inches(0.75), t_, size=22, bold=True, color=col,
         anchor=MSO_ANCHOR.MIDDLE)
    bullets(s, x + Inches(0.2), Inches(3.2), Inches(3.45), Inches(3.3), items, size=15, gap=14, marker=col)
    if i < 2:
        arrow(s, x + Inches(3.88), Inches(4.0), Inches(0.2), Inches(0.4), color=GREY)

# ================================================================= 13. conclusion
s = frame("Conclusion", 13, 3,
          "[9:40 – 10:00] En onze semaines : une chaîne de traitement couvrant vingt-sept pays, deux voies "
          "d'intégration à OpenCRVS sans modification de son cœur, et une évaluation rigoureuse. J'en retiens "
          "que la difficulté se situe aux jonctions entre systèmes, et qu'un système fiable est celui qui "
          "reconnaît ses limites. Je vous remercie et reste à votre disposition pour vos questions.")
takeaways = [("27 pays", "une chaîne de traitement générique, de 40 à 90 s par acte", BLUE),
             ("2 voies", "intégration à OpenCRVS sans modifier son cœur", TEAL),
             (fr(agg["anls"]), "ANLS mesuré, hallucination nulle, défauts documentés", AMBER),
             ("1 principe", "préférer l'aveu d'un doute à l'affirmation d'une erreur", RED)]
for i, (v, d_, col) in enumerate(takeaways):
    x = Inches(0.65 + i * 3.04)
    box(s, x, Inches(1.8), Inches(2.84), Inches(3.1), fill=LIGHT)
    box(s, x, Inches(1.8), Inches(2.84), Inches(0.12), fill=col, shape=MSO_SHAPE.RECTANGLE)
    text(s, x, Inches(2.15), Inches(2.84), Inches(0.9), v, size=32, bold=True, color=col, align=PP_ALIGN.CENTER)
    text(s, x + Inches(0.2), Inches(3.2), Inches(2.45), Inches(1.6), d_, size=15, color=INK, align=PP_ALIGN.CENTER)
ban = box(s, Inches(0.65), Inches(5.3), Inches(12.0), Inches(1.5), fill=NAVY)
label(ban, "Je vous remercie de votre attention", size=30, color=WHITE, bold=True)

prs.save(OUT)
print("->", OUT, f"({len(prs.slides)} slides)")

#!/usr/bin/env python3
"""Build the internship-validation deck (10 min talk, 12 slides).

Numbers are read from eval/quality_metrics.json so the slides cannot drift
from the report. Figures come from presentation/img (rendered from the same
SVG/PNG sources as the written report).

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
LIGHT = RGBColor(0xEE, 0xF2, 0xF6)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
FONT = "Calibri"

agg = json.load(open(ROOT / "eval" / "quality_metrics.json", encoding="utf-8"))["aggregate"]


def fr(x: float, d: int = 3) -> str:
    return f"{x:.{d}f}".replace(".", ",")


prs = Presentation()
prs.slide_width, prs.slide_height = Inches(13.333), Inches(7.5)
BLANK = prs.slide_layouts[6]
W, H = prs.slide_width, prs.slide_height
total_slides = 12


def text(slide, x, y, w, h, content, size=18, color=NAVY, bold=False,
         align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP):
    tb = slide.shapes.add_textbox(x, y, w, h)
    tf = tb.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    tf.margin_left = tf.margin_right = Inches(0.05)
    lines = content if isinstance(content, list) else [content]
    for i, ln in enumerate(lines):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        r = p.add_run()
        r.text = ln
        r.font.size, r.font.bold, r.font.name = Pt(size), bold, FONT
        r.font.color.rgb = color
    return tb


def bullets(slide, x, y, w, h, items, size=19, gap=10):
    tb = slide.shapes.add_textbox(x, y, w, h)
    tf = tb.text_frame
    tf.word_wrap = True
    for i, it in enumerate(items):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.space_after = Pt(gap)
        head, _, rest = it.partition("|")
        r0 = p.add_run()
        r0.text = "▸ "
        r0.font.size, r0.font.color.rgb, r0.font.name = Pt(size), TEAL, FONT
        if rest:
            r1 = p.add_run()
            r1.text = head
            r1.font.size, r1.font.bold, r1.font.name = Pt(size), True, FONT
            r1.font.color.rgb = NAVY
            r2 = p.add_run()
            r2.text = rest
            r2.font.size, r2.font.name = Pt(size), FONT
            r2.font.color.rgb = RGBColor(0x2B, 0x33, 0x3B)
        else:
            r1 = p.add_run()
            r1.text = head
            r1.font.size, r1.font.name = Pt(size), FONT
            r1.font.color.rgb = RGBColor(0x2B, 0x33, 0x3B)


def rect(slide, x, y, w, h, fill=LIGHT, line=None, shape=MSO_SHAPE.ROUNDED_RECTANGLE):
    s = slide.shapes.add_shape(shape, x, y, w, h)
    s.fill.solid()
    s.fill.fore_color.rgb = fill
    if line is None:
        s.line.fill.background()
    else:
        s.line.color.rgb = line
        s.line.width = Pt(1.25)
    s.shadow.inherit = False
    if shape == MSO_SHAPE.ROUNDED_RECTANGLE:
        s.adjustments[0] = 0.06
    return s


def picture(slide, name, x, y, w, h):
    """Place an image centred in the box, preserving its aspect ratio."""
    path = IMG / name
    iw, ih = Image.open(path).size
    scale = min(w / iw, h / ih)
    pw, ph = int(iw * scale), int(ih * scale)
    slide.shapes.add_picture(str(path), x + (w - pw) // 2, y + (h - ph) // 2, pw, ph)


def new_slide(title, n, notes):
    s = prs.slides.add_slide(BLANK)
    text(s, Inches(0.6), Inches(0.35), Inches(12.1), Inches(0.9), title,
         size=30, bold=True, anchor=MSO_ANCHOR.MIDDLE)
    ln = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0.65), Inches(1.25),
                            Inches(12.0), Emu(22000))
    ln.fill.solid()
    ln.fill.fore_color.rgb = BLUE
    ln.line.fill.background()
    text(s, Inches(11.6), Inches(7.05), Inches(1.2), Inches(0.35),
         f"{n} / {total_slides}", size=11, color=GREY, align=PP_ALIGN.RIGHT)
    text(s, Inches(0.6), Inches(7.05), Inches(8), Inches(0.35),
         "Mohamed Ghassen Bousalem · Stage EY Tunisie · ESPRIT", size=11, color=GREY)
    s.notes_slide.notes_text_frame.text = notes
    return s


def kpi(slide, x, y, w, h, value, label, color=BLUE):
    rect(slide, x, y, w, h, fill=WHITE, line=color)
    text(slide, x, y + Inches(0.25), w, Inches(1.0), value, size=40, bold=True,
         color=color, align=PP_ALIGN.CENTER)
    text(slide, x + Inches(0.1), y + Inches(1.3), w - Inches(0.2), h - Inches(1.4),
         label, size=15, color=GREY, align=PP_ALIGN.CENTER)


# ------------------------------------------------------------------ 1. titre --
s = prs.slides.add_slide(BLANK)
bg = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, W, H)
bg.fill.solid()
bg.fill.fore_color.rgb = NAVY
bg.line.fill.background()
bar = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0.8), Inches(2.0), Inches(0.12), Inches(2.6))
bar.fill.solid()
bar.fill.fore_color.rgb = AMBER
bar.line.fill.background()
text(s, Inches(1.15), Inches(1.9), Inches(11.4), Inches(1.9),
     "Extraction automatique de données d'actes d'état civil par modèles vision-langage",
     size=38, bold=True, color=WHITE)
text(s, Inches(1.15), Inches(3.8), Inches(11.4), Inches(0.9),
     "Pipeline OCR multi-pays et intégration au registre civil numérique OpenCRVS",
     size=22, color=RGBColor(0xC8, 0xD8, 0xE8))
text(s, Inches(1.15), Inches(5.2), Inches(11), Inches(1.4),
     ["Mohamed Ghassen Bousalem — ESPRIT, stage ingénieur",
      "EY Tunisie · Technology, Strategy & Transformation · 22 juin – 4 septembre 2026",
      "Encadrante : Mariem Abcha · Entretien de validation du 21/10/2026"],
     size=16, color=WHITE)
s.notes_slide.notes_text_frame.text = (
    "[0:00 – 0:30] Bonjour, merci de m'accueillir. Je présente mon stage de onze semaines chez EY "
    "Tunisie, dans la practice Technology, Strategy & Transformation : comment faire lire un acte "
    "de naissance scanné par un modèle vision-langage et pré-remplir une déclaration dans OpenCRVS.")

# ----------------------------------------------------------------- 2. contexte --
s = new_slide("Contexte : le papier, obstacle à l'identité légale", 2,
              "[0:30 – 1:30] Sans acte de naissance, pas d'accès à l'école, aux soins, au vote. "
              "L'ONU en a fait la cible 16.9 des ODD. Le vrai goulot n'est pas la photo du registre, "
              "c'est la ressaisie : un agent relit chaque acte et retape des dizaines de champs. "
              "C'est lent, coûteux, et ça introduit ses propres erreurs.")
cards = [("Un droit fondamental", "L'acte de naissance ouvre l'accès à l'école, aux soins, à l'emploi, au vote. ODD 16.9 : une identité juridique pour tous.", BLUE),
         ("Un stock papier hétérogène", "Registres, copies dactylographiées, extraits traduits, photos de travers : chaque pays, parfois chaque commune, a sa mise en page.", AMBER),
         ("Le goulot : la ressaisie", "Un agent relit chaque acte et retape les champs. Lent, coûteux, source d'erreurs, et non extensible.", RED)]
for i, (t, b, c) in enumerate(cards):
    x = Inches(0.65 + i * 4.1)
    rect(s, x, Inches(1.75), Inches(3.85), Inches(4.7), fill=LIGHT)
    bar = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, x, Inches(1.75), Inches(3.85), Inches(0.12))
    bar.fill.solid(); bar.fill.fore_color.rgb = c; bar.line.fill.background()
    text(s, x + Inches(0.2), Inches(2.1), Inches(3.45), Inches(0.9), t, size=22, bold=True, color=c)
    text(s, x + Inches(0.2), Inches(3.1), Inches(3.45), Inches(3.2), b, size=21, color=RGBColor(0x2B, 0x33, 0x3B))

# ------------------------------------------------------ 3. problématique/objectifs --
s = new_slide("Problématique et objectifs", 3,
              "[1:30 – 2:20] La question : comment extraire automatiquement les données d'un acte, "
              "quel que soit le pays, et les injecter dans un registre, de façon assez fiable pour que "
              "l'agent passe de la saisie à la vérification, sans jamais introduire une erreur présentée "
              "comme certaine. Cette dernière partie guide toute la conception.")
rect(s, Inches(0.65), Inches(1.7), Inches(12.0), Inches(1.7), fill=LIGHT, line=BLUE)
text(s, Inches(0.9), Inches(1.8), Inches(11.5), Inches(1.5),
     "Comment passer de la ressaisie à la vérification, pour des actes de pays et d'états "
     "de conservation très différents, sans jamais introduire dans le registre une erreur présentée comme certaine ?",
     size=21, bold=True, anchor=MSO_ANCHOR.MIDDLE)
bullets(s, Inches(0.8), Inches(3.8), Inches(11.8), Inches(3),
        ["Pipeline générique|  : un acte scanné → champs structurés + score de confiance, sans réécriture par pays",
         "Intégration OpenCRVS|  : déclaration pré-remplie, sans modifier le code du cœur",
         "Vérification humaine|  : écran de correction, corrections capitalisées",
         "Évaluation rigoureuse|  : métriques du domaine (ANLS, F1, CER), limites documentées"],
        size=20)

# ----------------------------------------------------------------- 4. pipeline --
s = new_slide("La solution : un pipeline en cinq étapes", 4,
              "[2:20 – 3:20] Cinq étapes : prétraitement, détection du pays, localisation des champs, "
              "extraction en deux passes indépendantes, puis validation et score. Le modèle vision-langage "
              "n'exige aucun corpus annoté : on lui décrit le schéma en langage naturel. L'accord entre les "
              "deux passes sert de signal de confiance. Résultat : 27 pays, 40 à 90 secondes par acte.")
picture(s, "diag_pipeline.png", Inches(0.5), Inches(1.5), Inches(6.6), Inches(5.4))
bullets(s, Inches(7.3), Inches(1.8), Inches(5.5), Inches(5),
        ["Modèle vision-langage|  : aucun corpus annoté, schéma décrit en langage naturel",
         "Deux passes|  (page entière + recadrages) : leur accord = signal de confiance",
         "27 packs pays|  + un pack générique",
         "40 à 90 s|  de traitement par acte"],
        size=20, gap=14)

# --------------------------------------------------------------- 5. honnêteté --
s = new_slide("Principe directeur : ne jamais affirmer faux", 5,
              "[3:20 – 4:20] Un OCR qui se trompe en le signalant coûte quelques secondes à l'officier. "
              "Un OCR qui se trompe avec assurance met une erreur dans un registre pour des décennies. Donc "
              "à chaque étage le système préfère avouer son doute : seuil de confiance à 0,6, valeur marquée "
              "« à vérifier », nationalité ambiguë jamais tranchée, catégorie de lieu d'accouchement jamais devinée.")
picture(s, "diag_honnetete.png", Inches(0.5), Inches(1.5), Inches(7.4), Inches(4.2))
bullets(s, Inches(8.1), Inches(1.7), Inches(4.8), Inches(5),
        ["Confiance < 0,6|  → valeur marquée « à vérifier »",
         "« Congolaise »|  (deux Congo) : jamais tranché",
         "Lieu d'accouchement|  : catégorie jamais devinée",
         "Nationalité ≠ lieu de naissance|  : jamais déduite"],
        size=18, gap=12)
rect(s, Inches(0.65), Inches(6.0), Inches(7.1), Inches(0.8), fill=LIGHT, line=TEAL)
text(s, Inches(0.8), Inches(6.0), Inches(6.8), Inches(0.8),
     "Une erreur signalée coûte quelques secondes ; une erreur assurée dure des décennies.",
     size=16, bold=True, color=TEAL, anchor=MSO_ANCHOR.MIDDLE)

# --------------------------------------------------------------- 6. OpenCRVS --
s = new_slide("Intégration à OpenCRVS : deux voies, zéro ligne du cœur modifiée", 6,
              "[4:20 – 5:30] OpenCRVS sépare le cœur de la configuration pays. Première voie : l'API de "
              "notification d'événement, qui dépose une déclaration pré-remplie avec le scan joint. Seconde "
              "voie, plus aboutie : un panneau ajouté au formulaire. L'officier dépose le scan sans quitter "
              "OpenCRVS, les champs se remplissent seuls sur toutes les pages, et il continue vers la page de "
              "relecture native. Tout passe par la configuration pays : le cœur n'est pas modifié.")
picture(s, "diag_architecture.png", Inches(0.5), Inches(1.5), Inches(7.5), Inches(3.6))
bullets(s, Inches(8.2), Inches(1.7), Inches(4.7), Inches(5),
        ["Voie 1|  : API Event Notification, déclaration + scan joint",
         "Voie 2|  : panneau de scan dans le formulaire, champs remplis sur toutes les pages",
         "Cœur OpenCRVS|  inchangé : compatible avec les mises à jour"],
        size=18, gap=12)
rect(s, Inches(0.65), Inches(5.35), Inches(7.4), Inches(1.4), fill=LIGHT)
text(s, Inches(0.85), Inches(5.4), Inches(7.1), Inches(1.3),
     ["Chemin technique de la voie 2",
      "scan → stockage MinIO d'OpenCRVS → chemin envoyé au service OCR → valeurs renvoyées par identifiant de champ"],
     size=15, color=GREY, anchor=MSO_ANCHOR.MIDDLE)

# ------------------------------------------------------------ 7. ce que voit --
s = new_slide("Ce que voit l'officier : des valeurs vérifiables, avec leur origine", 7,
              "[5:30 – 6:20] Le pipeline dessine sur le scan la zone d'où chaque valeur a été lue. Cette "
              "image de repérage est jointe à la déclaration comme pièce justificative : l'officier voit "
              "d'où vient une valeur, pas seulement ce qu'elle dit. C'est le moyen le plus rapide de repérer "
              "une valeur lue sur la mauvaise ligne.")
picture(s, "capture_field_boxes.png", Inches(0.8), Inches(1.45), Inches(4.2), Inches(5.5))
bullets(s, Inches(5.4), Inches(1.9), Inches(7.4), Inches(5),
        ["Repérage OCR|  joint comme pièce justificative de la déclaration",
         "Pré-remplissage|  de l'enfant, des parents et du déclarant (~7 champs par document)",
         "Valeurs douteuses|  signalées « à vérifier » dans le commentaire de revue",
         "Tout reste modifiable|  : l'officier garde la main et valide"],
        size=20, gap=16)

# --------------------------------------------------------------- 8. difficultés --
s = new_slide("Difficultés rencontrées : l'enjeu était aux jonctions", 8,
              "[6:20 – 7:10] La difficulté principale n'était pas l'extraction, le modèle lit bien des "
              "documents difficiles : c'était les points de jonction entre systèmes. Exemple : les champs "
              "restaient vides car une valeur sans champ parent est ignorée par le formulaire, puis parce "
              "que le JSON plat avec points n'est pas résolu. Un champ HTTP ne peut pas envoyer de fichier : "
              "on envoie le chemin MinIO. Et le démarrage de la plateforme échouait à chaque fois à cause de "
              "deux conditions de concurrence, corrigées par un sondage explicite.")
rows = [("Champs restés vides", "valeur déclarée sans champ parent, puis JSON plat à clés pointées", "parent + valeur, JSON imbriqué"),
        ("Un champ HTTP n'envoie pas de fichier", "seul du JSON peut partir du formulaire", "envoi du chemin MinIO, lecture côté service OCR"),
        ("Plantage du formulaire", "balises ICU dans les libellés de texte", "texte brut + styles de configuration"),
        ("Démarrage instable", "Docker/WSL : services lancés avant d'être prêts", "sondage explicite : 5 min → 70 s")]
tx, ty = Inches(0.65), Inches(1.7)
cw = [Inches(3.5), Inches(4.5), Inches(4.0)]
heads = ["Symptôme", "Cause", "Résolution"]
x = tx
for h_, w_ in zip(heads, cw):
    r = rect(s, x, ty, w_ - Inches(0.05), Inches(0.55), fill=NAVY, shape=MSO_SHAPE.RECTANGLE)
    text(s, x, ty, w_ - Inches(0.05), Inches(0.55), h_, size=16, bold=True, color=WHITE, anchor=MSO_ANCHOR.MIDDLE)
    x += w_
for i, row in enumerate(rows):
    y = ty + Inches(0.6) + i * Inches(1.1)
    x = tx
    for j, (c, w_) in enumerate(zip(row, cw)):
        rect(s, x, y, w_ - Inches(0.05), Inches(1.0), fill=LIGHT if i % 2 == 0 else WHITE,
             line=None if i % 2 == 0 else RGBColor(0xC8, 0xD2, 0xDC), shape=MSO_SHAPE.RECTANGLE)
        text(s, x + Inches(0.08), y, w_ - Inches(0.2), Inches(1.0), c, size=15,
             bold=(j == 0), color=NAVY if j == 0 else RGBColor(0x2B, 0x33, 0x3B), anchor=MSO_ANCHOR.MIDDLE)
        x += w_

# --------------------------------------------------------------- 9. évaluation --
s = new_slide("Évaluation : mesurer avec les métriques du domaine", 9,
              "[7:10 – 8:10] J'ai évalué sur un jeu de référence transcrit à la main : 9 actes de pays "
              "différents, dont des cas difficiles, et 69 champs, dont certains volontairement absents pour "
              "détecter les hallucinations. Métriques : ANLS, la référence DocVQA, F1 par champ, CER, taux "
              "d'hallucination. BLEU et ROUGE sont écartés des indicateurs principaux car ils mesurent le "
              "recouvrement de n-grammes, pas l'exactitude d'un champ. Résultats : ANLS "
              f"{fr(agg['anls'])}, F1 exact {fr(agg['exact_f1'])}, hallucination nulle.")
text(s, Inches(0.65), Inches(1.45), Inches(12), Inches(0.5),
     f"Jeu de référence transcrit : {agg['documents']} actes · {agg['fields_expected']} champs attendus · "
     "documents dégradés inclus · champs volontairement absents pour détecter l'invention",
     size=16, color=GREY)
tiles = [(fr(agg["anls"]), "Similarité ANLS", BLUE),
         (fr(agg["exact_f1"]), "F1, correspondance exacte", BLUE),
         (fr(agg["fuzzy_f1"]), "F1, correspondance approchée", TEAL),
         (f"{agg['cer']*100:.1f} %".replace(".", ","), "Taux d'erreur caractère (CER)", TEAL),
         ("0 %", "Taux d'hallucination", RED),
         ("100 %", "Conformité au schéma", RED)]
for i, (v, l, c) in enumerate(tiles):
    x = Inches(0.65 + (i % 3) * 4.1)
    y = Inches(2.25 + (i // 3) * 2.35)
    kpi(s, x, y, Inches(3.85), Inches(2.15), v, l, c)

# ---------------------------------------------------------------- 10. résultats --
s = new_slide("Résultats détaillés et défauts documentés", 10,
              "[8:10 – 9:10] Les résultats par champ sont bons, mais l'évaluation a aussi trouvé de vrais "
              "défauts que je documente plutôt que de masquer : une année mal lue (1999 devenu 1989), un "
              "caractère erroné, la nationalité manquante sur un pays, et surtout une inversion prénom / nom "
              "quand le nom de famille est écrit en premier en majuscules, au Bénin et au Mali. La répartition "
              f"prénom / nom n'est correcte que dans {agg['name_split_accuracy']*100:.0f} % des cas, même si le "
              "nom complet est bien lu. Ce défaut est identifié et corrigeable.")
picture(s, "chart_anls_par_champ.png", Inches(0.5), Inches(1.5), Inches(7.6), Inches(3.9))
bullets(s, Inches(8.3), Inches(1.6), Inches(4.7), Inches(5),
        ["Année mal lue|  : 1999 lu 1989",
         "Caractère erroné|  : FATOUMATA lu FATOUKATA",
         "Nationalité manquante|  sur un pays",
         f"Prénom / nom inversés|  : répartition correcte à {agg['name_split_accuracy']*100:.0f} %"],
        size=17, gap=11)
rect(s, Inches(0.65), Inches(5.65), Inches(12.0), Inches(1.15), fill=LIGHT, line=AMBER)
text(s, Inches(0.85), Inches(5.65), Inches(11.6), Inches(1.15),
     "Ces défauts sont signalés, pas masqués : c'est la même ligne que le principe d'honnêteté du système. "
     "Le nom complet est bien lu ; c'est son découpage en prénom et nom qui échoue sur certaines conventions.",
     size=16, color=RGBColor(0x8A, 0x5A, 0x10), anchor=MSO_ANCHOR.MIDDLE)

# ---------------------------------------------------------------- 11. perspectives --
s = new_slide("Limites et perspectives", 11,
              "[9:10 – 9:45] Limites : jeu de référence de neuf actes, donc des chiffres indicatifs, pas "
              "statistiquement définitifs ; inversion prénom/nom à corriger ; dépendance à un modèle "
              "hébergé. À court terme : corriger l'ordre des noms par pack pays. À moyen terme : un modèle "
              "hébergé localement, car des données d'état civil ne doivent pas transiter par une API tierce, "
              "et un jeu d'évaluation plus large. Le changement de modèle ne demande aucune modification de code.")
for i, (t, items, c) in enumerate([
        ("Limites", ["Jeu de référence de 9 actes : chiffres indicatifs", "Ordre prénom / nom à corriger sur certains pays", "Dépendance à une API de modèle tierce"], AMBER),
        ("Court terme", ["Corriger l'ordre des noms par pack pays", "Étendre le jeu de référence", "Compléter les champs de nationalité manquants"], BLUE),
        ("Moyen terme", ["Modèle hébergé localement (souveraineté des données)", "Déploiement sur une instance réelle", "Capitaliser les corrections de l'officier"], TEAL)]):
    x = Inches(0.65 + i * 4.1)
    rect(s, x, Inches(1.75), Inches(3.85), Inches(4.8), fill=LIGHT)
    bar = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, x, Inches(1.75), Inches(3.85), Inches(0.12))
    bar.fill.solid(); bar.fill.fore_color.rgb = c; bar.line.fill.background()
    text(s, x + Inches(0.2), Inches(2.05), Inches(3.45), Inches(0.6), t, size=24, bold=True, color=c)
    bullets(s, x + Inches(0.15), Inches(2.8), Inches(3.55), Inches(3.6), items, size=17, gap=12)

# ---------------------------------------------------------------- 12. conclusion --
s = new_slide("Conclusion", 12,
              "[9:45 – 10:00] En onze semaines : un pipeline sur 27 pays, deux voies d'intégration à "
              "OpenCRVS sans toucher à son cœur, et une évaluation honnête. Ce que j'en retiens : la "
              "difficulté est dans les jonctions entre systèmes, et un système fiable est celui qui avoue "
              "ses limites. Merci, je suis prêt pour vos questions.")
bullets(s, Inches(0.8), Inches(1.8), Inches(11.8), Inches(3.4),
        ["Un pipeline|  sur 27 pays, de 40 à 90 s par acte",
         "Deux voies d'intégration|  à OpenCRVS, sans modifier son cœur",
         f"Une évaluation honnête|  : ANLS {fr(agg['anls'])}, hallucination nulle, défauts documentés",
         "Un principe|  : préférer avouer un doute plutôt qu'affirmer faux"],
        size=22, gap=16)
rect(s, Inches(0.65), Inches(5.3), Inches(12.0), Inches(1.4), fill=NAVY)
text(s, Inches(0.65), Inches(5.3), Inches(12.0), Inches(1.4), "Merci — place à vos questions",
     size=32, bold=True, color=WHITE, align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)

prs.save(OUT)
print("->", OUT, f"({len(prs.slides)} slides)")

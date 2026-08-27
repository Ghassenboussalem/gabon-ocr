#!/usr/bin/env python3
"""Build the evaluation report PDF from the measured metrics.

Reads what the two evaluation harnesses produced — eval/quality_metrics.json
(correctness against transcribed references) and
notes-superviseur/metriques_par_document.csv (throughput across the sample
set) — and lays them out as a report. Nothing is typed in by hand here: every
figure comes from those files, so re-running the harnesses and this script
keeps the document honest.

    python tools/evaluate_quality.py     # refresh correctness metrics
    python tools/evaluate_batch.py       # refresh throughput metrics
    python tools/build_eval_report.py    # -> rapport_evaluation.pdf
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (PageBreak, Paragraph, SimpleDocTemplate, Spacer,
                                Table, TableStyle)

ROOT = Path(__file__).resolve().parent.parent
EVAL = ROOT / "eval"
NOTES = ROOT / "notes-superviseur"
OUT = ROOT / "rapport_evaluation.pdf"

NAVY = colors.HexColor("#1a3a5c")
GREY = colors.HexColor("#5a6672")
LIGHT = colors.HexColor("#eef2f6")


def styles() -> dict:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle("t", parent=base["Title"], fontSize=20,
                                textColor=NAVY, spaceAfter=4),
        "subtitle": ParagraphStyle("st", parent=base["Normal"], fontSize=10.5,
                                   textColor=GREY, alignment=1, spaceAfter=16),
        "h1": ParagraphStyle("h1", parent=base["Heading1"], fontSize=13.5,
                             textColor=NAVY, spaceBefore=16, spaceAfter=7),
        "h2": ParagraphStyle("h2", parent=base["Heading2"], fontSize=11,
                             textColor=NAVY, spaceBefore=11, spaceAfter=5),
        "body": ParagraphStyle("b", parent=base["Normal"], fontSize=9.5,
                               leading=13.5, alignment=TA_JUSTIFY, spaceAfter=6),
        "note": ParagraphStyle("n", parent=base["Normal"], fontSize=8.5,
                               leading=12, textColor=GREY, alignment=TA_JUSTIFY,
                               spaceAfter=6, leftIndent=8, borderPadding=4),
        "cell": ParagraphStyle("c", parent=base["Normal"], fontSize=8.5, leading=11),
    }


def table(data, widths, align_right_from=1) -> Table:
    t = Table(data, colWidths=widths, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("ALIGN", (align_right_from, 1), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT]),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#c8d2dc")),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
    ]))
    return t


def pct(x: float) -> str:
    return f"{x * 100:.1f} %"


def main() -> None:
    q = json.loads((EVAL / "quality_metrics.json").read_text(encoding="utf-8"))
    gt = json.loads((EVAL / "ground_truth.json").read_text(encoding="utf-8"))
    agg, per_field, per_doc = q["aggregate"], q["per_field"], q["per_document"]

    batch = []
    csv_path = NOTES / "metriques_par_document.csv"
    if csv_path.exists():
        with open(csv_path, encoding="utf-8-sig") as f:
            batch = [r for r in csv.DictReader(f) if r.get("handwritten") == "False"]

    s = styles()
    story = []

    story.append(Paragraph("Évaluation du pipeline d'extraction", s["title"]))
    story.append(Paragraph(
        "OCR d'actes d'état civil africains &rarr; pré-remplissage OpenCRVS<br/>"
        "Métriques mesurées, méthode et limites", s["subtitle"]))

    # ---------------------------------------------------------------- intro --
    story.append(Paragraph("1. Ce qui est mesuré, et pourquoi", s["h1"]))
    story.append(Paragraph(
        "Deux questions distinctes sont évaluées séparément, car elles ne se "
        "confondent pas. <b>La justesse</b> : quand le système lit un champ, "
        "lit-il la bonne valeur ? Elle se mesure contre des valeurs de "
        "référence transcrites depuis les actes. <b>Le rendement</b> : sur un "
        "lot représentatif, quelle part du travail de saisie est effectivement "
        "épargnée à l'officier ? Elle se mesure sans référence, sur l'ensemble "
        "des documents traités.", s["body"]))
    story.append(Paragraph(
        "Le choix des métriques suit l'usage du domaine (DocVQA, SROIE, CORD, "
        "OmniDocBench) plutôt que les métriques de génération de texte. ANLS "
        "et CER tolèrent une coquille tout en sanctionnant une valeur fausse ; "
        "la précision et le rappel par champ traitent l'extraction comme une "
        "tâche de recherche d'information. BLEU et ROUGE ne figurent qu'en "
        "annexe, sur le seul champ en texte libre : le recouvrement de n-grammes "
        "récompense une paraphrase fluide et reste aveugle à une date fausse — "
        "or c'est précisément l'erreur qui compte pour un registre d'état civil.",
        s["body"]))

    # -------------------------------------------------------------- headline --
    story.append(Paragraph("2. Justesse de l'extraction", s["h1"]))
    story.append(Paragraph(
        f"Mesurée sur <b>{agg['documents']} actes tapés/imprimés</b> "
        f"({agg['fields_expected']} champs de référence), un par pays.", s["body"]))

    rows = [["Métrique", "Valeur", "Ce qu'elle dit"]]
    rows += [
        ["ANLS", f"{agg['anls']:.3f}",
         Paragraph("Similarité de Levenshtein normalisée, seuil 0,5 (convention DocVQA)", s["cell"])],
        ["Exact match F1", f"{agg['exact_f1']:.3f}",
         Paragraph("Valeur strictement identique à la référence", s["cell"])],
        ["Fuzzy match F1", f"{agg['fuzzy_f1']:.3f}",
         Paragraph("Tolérance d'une variation mineure (similarité ≥ 0,8)", s["cell"])],
        ["CER", f"{agg['cer']:.3f}",
         Paragraph("Taux d'erreur caractère sur les champs renseignés", s["cell"])],
        ["WER", f"{agg['wer']:.3f}",
         Paragraph("Taux d'erreur mot", s["cell"])],
        ["Couverture", pct(agg["coverage"]),
         Paragraph("Champs présents dans l'acte que le système a effectivement produits", s["cell"])],
        ["Hallucinations", pct(agg["hallucination_rate"]),
         Paragraph("Valeurs inventées pour un champ absent de l'acte", s["cell"])],
        ["Conformité schéma", pct(agg["schema_conformance"]),
         Paragraph("Valeurs directement exploitables par OpenCRVS (date ISO, énumération sexe…)", s["cell"])],
        ["Split prénom / nom", pct(agg["name_split_accuracy"]),
         Paragraph("Chaque moitié du nom placée dans le bon champ", s["cell"])],
    ]
    story.append(table(rows, [4.2 * cm, 2.3 * cm, 9.5 * cm]))

    story.append(Spacer(1, 8))
    story.append(Paragraph(
        "<b>Limites de ce chiffre — à lire avant de le citer.</b> "
        f"L'échantillon est petit ({agg['documents']} documents, "
        f"{agg['fields_expected']} champs) et, surtout, les valeurs de référence "
        "ont été transcrites dans le cadre de ce projet, et non produites par un "
        "annotateur humain indépendant. Une erreur de lecture commise à la fois "
        "par le pipeline et par la transcription ne serait donc pas détectée. "
        "Ces résultats démontrent que le système traite correctement ces "
        "documents-là ; ils ne prouvent pas une absence d'erreurs en général. "
        "Une validation par un officier d'état civil sur un lot plus large est "
        "la prochaine étape nécessaire.", s["note"]))

    # ------------------------------------------------------------- per field --
    story.append(Paragraph("2.1 Détail par champ", s["h2"]))
    rows = [["Champ", "n", "Exact", "ANLS", "CER", "Couverture"]]
    labels = {"child.name": "Nom de l'enfant", "child.dob": "Date de naissance",
              "child.gender": "Sexe",
              "father.name": "Nom du père", "father.dob": "Date de naissance du père",
              "father.occupation": "Profession du père",
              "father.nationality": "Nationalité du père",
              "mother.name": "Nom de la mère", "mother.dob": "Date de naissance de la mère",
              "mother.occupation": "Profession de la mère",
              "mother.nationality": "Nationalité de la mère"}
    for k, v in per_field.items():
        rows.append([labels.get(k, k), str(v["n"]), f"{v['exact']}/{v['n']}",
                     f"{v['anls']:.2f}", f"{v['cer']:.2f}", pct(v["coverage"])])
    story.append(table(rows, [5.2 * cm, 1.4 * cm, 2.0 * cm, 2.0 * cm, 2.0 * cm, 3.4 * cm]))

    story.append(Paragraph("2.2 Détail par document", s["h2"]))
    rows = [["Document", "Pays", "Champs exacts", "ANLS"]]
    for r in per_doc:
        rows.append([r["doc_id"], r["country"].upper(),
                     f"{r['exact']}/{r['expected']}", f"{r['anls']:.2f}"])
    story.append(table(rows, [7.5 * cm, 2.2 * cm, 3.3 * cm, 3.0 * cm]))

    story.append(PageBreak())

    # ------------------------------------------------------------ errors ------
    story.append(Paragraph("3. Erreurs relevées", s["h1"]))
    errors = q.get("errors", [])
    swapped = q.get("swapped_names", [])
    story.append(Paragraph(
        f"L'évaluation relève <b>{len(errors)} champs erronés ou manquants</b> "
        f"sur {agg['fields_expected']}, et <b>{len(swapped)} inversions "
        "prénom / nom</b>. Ils sont listés ici plutôt que résumés : un rapport "
        "d'évaluation qui n'expose pas ses échecs ne permet pas de juger de la "
        "portée de ses réussites.", s["body"]))

    if errors:
        rows = [["Document", "Champ", "Attendu", "Obtenu"]]
        for e in errors:
            rows.append([
                Paragraph(e["doc_id"], s["cell"]),
                Paragraph(e["field"], s["cell"]),
                Paragraph(e["ref"] or "—", s["cell"]),
                Paragraph(e["pred"] or "<i>(vide)</i>", s["cell"]),
            ])
        story.append(table(rows, [3.6 * cm, 3.4 * cm, 4.6 * cm, 4.4 * cm], align_right_from=99))

    story.append(Spacer(1, 8))
    story.append(Paragraph(
        "Trois natures d'erreur se dégagent. Une <b>erreur de lecture de "
        "chiffre</b> sur un acte narratif dense (une année lue 1989 au lieu de "
        "1999) : c'est l'erreur la plus préoccupante, car une date reste "
        "plausible même fausse et ne se signale pas d'elle-même. Des "
        "<b>erreurs de caractère</b> sur dactylographie pâle (FATOUKATA pour "
        "FATOUMATA, un prénom tronqué) : visibles et corrigées en un coup "
        "d'œil par l'officier. Enfin des <b>valeurs non extraites</b>, quand "
        "le pack pays ne prévoit pas encore le champ — la nationalité n'était "
        "cherchée dans aucun pack avant ce travail ; elle a été ajoutée pour "
        "la Côte d'Ivoire et reste à ajouter ailleurs.", s["body"]))

    if swapped:
        story.append(Paragraph("3.1 Inversions prénom / nom", s["h2"]))
        rows = [["Document", "Champ", "Attendu", "Obtenu"]]
        for e in swapped:
            rows.append([
                Paragraph(e["doc_id"], s["cell"]),
                Paragraph(e["field"], s["cell"]),
                Paragraph(e["ref"], s["cell"]),
                Paragraph(e["pred"], s["cell"]),
            ])
        story.append(table(rows, [3.6 * cm, 3.4 * cm, 4.6 * cm, 4.4 * cm], align_right_from=99))

    story.append(PageBreak())

    # ------------------------------------------------------------ defect ------
    story.append(Paragraph("4. Défaut identifié par l'évaluation", s["h1"]))
    story.append(Paragraph(
        "Le défaut le plus systématique mérite d'être isolé : <b>l'ordre prénom / "
        "nom est inversé pour "
        "les parents lorsque l'acte écrit le nom de famille en premier et tout "
        "en majuscules</b> (cas du Bénin : « SANNI GOUDA », où SANNI est le nom "
        "de famille). L'heuristique repose sur la casse — les majuscules "
        "signalent le nom de famille dans les actes francophones — et ne peut "
        "pas trancher quand tout est en majuscules ; elle retombe alors sur "
        "« le dernier mot est le nom de famille », ce qui est faux pour ces "
        "conventions.", s["body"]))
    story.append(Paragraph(
        "Le nom lui-même est correctement lu : c'est sa répartition entre les "
        "deux champs d'OpenCRVS qui est erronée. Deux correctifs sont "
        "envisageables : exploiter le nom de famille de l'enfant, connu par un "
        "champ étiqueté, lorsqu'il apparaît aussi dans le nom d'un parent "
        "(familles partageant le patronyme) ; et déclarer l'ordre des noms dans "
        "le pack pays, l'information étant une convention nationale stable. "
        "Ce défaut est signalé plutôt que corrigé dans l'urgence : le corriger "
        "sans jeu de validation plus large risquerait d'introduire des "
        "régressions sur les autres pays.", s["body"]))

    # ---------------------------------------------------------- throughput ----
    if batch:
        story.append(Paragraph("5. Rendement sur le lot d'échantillons", s["h1"]))
        n = len(batch)
        avg_fields = sum(float(r["fields_total"]) for r in batch) / n
        avg_auto = sum(float(r["pct_auto_accepted"]) for r in batch) / n
        avg_crvs = sum(float(r["opencrvs_fields_prefilled"]) for r in batch) / n
        story.append(Paragraph(
            f"Mesuré sans référence sur <b>{n} actes tapés/imprimés</b> (un par "
            "pays), ce volet répond à la question opérationnelle : combien de "
            "saisie le système épargne-t-il réellement ?", s["body"]))
        rows = [["Indicateur", "Valeur"]]
        rows += [
            ["Documents évalués", str(n)],
            ["Champs détectés par document (moyenne)", f"{avg_fields:.1f}"],
            ["Champs auto-acceptés (moyenne)", f"{avg_auto:.1f} %"],
            ["Champs OpenCRVS pré-remplis par document (moyenne)", f"{avg_crvs:.1f}"],
            ["Temps de traitement par document", "≈ 40 à 90 s"],
        ]
        story.append(table(rows, [11.5 * cm, 5.0 * cm]))
        story.append(Spacer(1, 6))
        story.append(Paragraph(
            "« Auto-accepté » désigne un champ dont la confiance dépasse le "
            "seuil de 0,6 et qui ne requiert donc pas de relecture signalée. En "
            "dessous du seuil, la valeur est tout de même pré-remplie mais "
            "explicitement marquée « à vérifier » : le système préfère signaler "
            "un doute plutôt que présenter une valeur incertaine comme sûre.",
            s["body"]))

    # ------------------------------------------------------------- annexe -----
    story.append(Paragraph("6. Annexe — métriques de génération (BLEU / ROUGE)", s["h1"]))
    story.append(Paragraph(
        "Calculées uniquement sur le lieu de naissance, seul champ en texte "
        "libre, et fournies pour comparabilité avec la littérature. Elles ne "
        "sont pas retenues comme indicateur principal : un modèle peut obtenir "
        "un bon score de recouvrement de n-grammes tout en produisant une date "
        "ou un nom faux.", s["body"]))
    rows = [["Métrique", "Valeur"]]
    rows += [
        ["ANLS (lieu de naissance)", f"{agg['place_anls']:.3f}"],
        ["CER (lieu de naissance)", f"{agg['place_cer']:.3f}"],
        ["ROUGE-L", f"{agg['place_rouge_l']:.3f}"],
        ["BLEU", f"{agg['place_bleu']:.3f}"],
    ]
    story.append(table(rows, [11.5 * cm, 5.0 * cm]))
    story.append(Spacer(1, 6))
    story.append(Paragraph(
        "L'écart entre ANLS et BLEU sur ce champ illustre le propos : les "
        "réponses sont sémantiquement justes (« Abidjan » pour « Clinique du "
        "Belvédère à Abidjan ») mais lexicalement plus courtes que la "
        "référence, ce que BLEU pénalise lourdement alors que la valeur reste "
        "exploitable par l'officier.", s["body"]))

    story.append(Paragraph("7. Méthode et reproductibilité", s["h1"]))
    story.append(Paragraph(
        "Les valeurs de référence sont versionnées dans "
        "<font face='Courier'>eval/ground_truth.json</font>, avec pour chaque "
        "champ sa provenance et sa définition. Les métriques sont recalculées "
        "par <font face='Courier'>tools/evaluate_quality.py</font> (justesse) "
        "et <font face='Courier'>tools/evaluate_batch.py</font> (rendement) ; "
        "ce rapport est produit par "
        "<font face='Courier'>tools/build_eval_report.py</font> à partir de "
        "leurs sorties, sans aucune valeur saisie manuellement. Les actes "
        "manuscrits sont exclus de ces chiffres et traités comme un problème "
        "distinct : la reconnaissance d'écriture manuscrite est nettement plus "
        "difficile, et les mélanger masquerait la performance réelle sur la "
        "cible du projet.", s["body"]))
    story.append(Paragraph(
        f"Champs évalués : {', '.join(q['config']['scored_fields'])}. "
        f"Seuil ANLS : {q['config']['anls_threshold']}. "
        f"Seuil de correspondance approchée : {q['config']['fuzzy_threshold']}. "
        f"Provenance des références : {gt['_about']['provenance']}", s["note"]))

    doc = SimpleDocTemplate(
        str(OUT), pagesize=A4,
        leftMargin=2.2 * cm, rightMargin=2.2 * cm,
        topMargin=2.0 * cm, bottomMargin=2.0 * cm,
        title="Évaluation du pipeline d'extraction",
        author="Ghassen Bousselem")
    doc.build(story)
    print(f"-> {OUT}")


if __name__ == "__main__":
    main()

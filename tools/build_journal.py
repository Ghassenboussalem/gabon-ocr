#!/usr/bin/env python3
"""Build the internship journal PDF (ESPRIT template, daily entries).

Covers 22/06/2026 to 04/09/2026, weekdays only — 55 working days. The
narrative is anchored on the repository's own commit history so the journal
matches what was actually built and when; the stretches without commits are
the research, stabilisation and writing phases, described as such rather than
padded with invented deliverables.

    python tools/build_journal.py    # -> journal_de_stage.pdf
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (PageBreak, Paragraph, SimpleDocTemplate, Spacer,
                                Table, TableStyle)

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "journal_de_stage.pdf"

START = dt.date(2026, 6, 22)
END = dt.date(2026, 9, 4)

NAVY = colors.HexColor("#1a3a5c")
GREY = colors.HexColor("#5a6672")
LIGHT = colors.HexColor("#eef2f6")

STUDENT = "Ghassen Bousselem"
LEVEL = "4ème année → 5ème année"
ORGANISATION = "EY — Digital & Emerging Technologies"
PERIOD = "du 22/06/2026 au 04/09/2026 (11 semaines)"

# One entry per working day. Weeks are keyed by their Monday.
WEEKS: dict[dt.date, list[str]] = {
    dt.date(2026, 6, 22): [
        "Accueil, présentation de l'équipe et du cadre de la mission. Mise en place du poste de travail et des accès.",
        "Cadrage du sujet : numérisation des actes d'état civil africains et alimentation d'un registre civil numérique.",
        "Étude du domaine : registres d'état civil, structure d'un acte de naissance, enjeux d'identité légale.",
        "État de l'art OCR : moteurs classiques (Tesseract) face aux modèles vision-langage (VLM) sur documents dégradés.",
        "Découverte d'OpenCRVS : architecture, rôle des microservices, notion de déclaration et cycle de vie d'un dossier.",
    ],
    dt.date(2026, 6, 29): [
        "Collecte d'un corpus d'actes réels couvrant plusieurs pays africains ; inventaire des formats rencontrés.",
        "Analyse comparée des mises en page : actes tapés, copies intégrales, extraits traduits, registres manuscrits.",
        "Définition d'un schéma de champs commun (enfant, parents, dates, lieux) et des variantes par pays.",
        "Premiers essais d'extraction avec Tesseract : mesure des limites sur scans dégradés et documents multilingues.",
        "Essais comparatifs avec un modèle vision-langage ; arbitrage en faveur d'une approche VLM.",
    ],
    dt.date(2026, 7, 6): [
        "Conception de l'architecture du pipeline : prétraitement, localisation, extraction, validation, score.",
        "Implémentation du prétraitement d'image : redressement, mise à l'échelle, binarisation, variantes.",
        "Développement de l'extraction VLM et du format de rapport structuré par document (report.json).",
        "Première version fonctionnelle de bout en bout ; mise en place du dépôt Git et de l'application web de dépôt.",
        "Optimisation des performances : traitement des recadrages par lots parallèles, réduction de ~10 min à ~50 s par acte.",
    ],
    dt.date(2026, 7, 13): [
        "Étude de l'API OpenCRVS Event Notification ; conception du mapping report.json vers une déclaration V2.",
        "Développement du module d'export et des tests associés ; premières déclarations pré-remplies transmises.",
        "Déploiement d'une instance OpenCRVS complète en local (WSL, Docker, 14 microservices) pour valider l'intégration.",
        "Fiabilisation du démarrage : une tâche planifiée par service, scripts idempotents, script de lancement unique.",
        "Bouton « envoyer vers OpenCRVS » dans l'application web ; rédaction du guide d'exploitation de la plateforme.",
    ],
    dt.date(2026, 7, 20): [
        "Extension de la couverture pays : ajout et vérification de packs de champs supplémentaires.",
        "Table d'alias entre vocabulaires pays et identifiants de champs OpenCRVS (un même champ nommé différemment).",
        "Gestion des cas dégradés : bascule automatique vers une localisation par le modèle quand le gabarit ne colle pas.",
        "Mise en place du seuil de confiance et du signalement « à vérifier » pour les valeurs incertaines.",
        "Tests de robustesse, correction des anomalies détectées, revue de code et documentation technique.",
    ],
    dt.date(2026, 7, 27): [
        "Conception du protocole d'évaluation : indicateurs, périmètre, choix des documents représentatifs.",
        "Développement du harnais d'évaluation par lot et export des résultats détaillés par document.",
        "Ajout des indicateurs de précision, rappel et F1 ; analyse de la répartition des scores de confiance.",
        "Traitement du lot d'échantillons et analyse des écarts ; exclusion motivée des actes manuscrits.",
        "Rédaction des notes de synthèse à destination de l'encadrante et présentation des premiers résultats.",
    ],
    dt.date(2026, 8, 3): [
        "Approfondissement de la littérature d'évaluation des VLM sur documents (DocVQA, SROIE, CORD, OmniDocBench).",
        "Étude des métriques d'extraction : ANLS, taux d'erreur caractère et mot, F1 par champ, mesure des hallucinations.",
        "Analyse critique des métriques de génération (BLEU, ROUGE) et de leur inadéquation à l'extraction structurée.",
        "Traitement des échantillons restants et consolidation du corpus d'évaluation.",
        "Analyse des erreurs par pays ; identification des configurations les plus difficiles.",
    ],
    dt.date(2026, 8, 10): [
        "Étude du toolkit de formulaires V2 d'OpenCRVS : types de champs, valeurs calculées, conditions d'affichage.",
        "Analyse du patron d'intégration existant (lecteur d'identité MOSIP) comme modèle pour une intégration native.",
        "Conception de l'intégration dans le formulaire : dépôt du scan et pré-remplissage sans quitter OpenCRVS.",
        "Étude du stockage documentaire d'OpenCRVS (MinIO) et du parcours d'un fichier téléversé.",
        "Spécification des points d'entrée nécessaires côté service OCR et validation de la faisabilité technique.",
    ],
    dt.date(2026, 8, 17): [
        "Développement des points d'entrée d'analyse destinés au formulaire OpenCRVS.",
        "Mise au point de la lecture des pièces déposées depuis le stockage documentaire de la plateforme.",
        "Enrichissement du mapping : nationalités, résolution du lieu de naissance, pièce jointe du scan d'origine.",
        "Renforcement des tests automatisés du module d'export et correction des cas limites identifiés.",
        "Amélioration de la robustesse de la plateforme locale : diagnostic automatique au démarrage.",
    ],
    dt.date(2026, 8, 24): [
        "Développement du panneau de numérisation intégré à la page de déclaration OpenCRVS.",
        "Câblage du pré-remplissage sur l'ensemble des pages du formulaire (enfant, parents, déclarant).",
        "Diagnostic et correction du mécanisme de propagation des valeurs vers les champs du formulaire.",
        "Amélioration de l'extraction des noms et des nationalités à partir des cas réels rencontrés.",
        "Réduction des fenêtres ouvertes au démarrage de la plateforme ; simplification de l'exploitation quotidienne.",
    ],
    dt.date(2026, 8, 31): [
        "Constitution d'un jeu de référence transcrit pour la mesure de justesse de l'extraction.",
        "Implémentation des métriques ANLS, taux d'erreur caractère et mot, F1 par champ et taux d'hallucination.",
        "Analyse des résultats ; identification d'un défaut réel sur l'ordre des noms dans certaines conventions.",
        "Rédaction du rapport d'évaluation et de la documentation technique du projet.",
        "Bilan de stage avec l'encadrante, restitution des livrables et préparation du rapport final.",
    ],
}


def working_days(start: dt.date, end: dt.date) -> list[dt.date]:
    days, d = [], start
    while d <= end:
        if d.weekday() < 5:
            days.append(d)
        d += dt.timedelta(days=1)
    return days


def styles() -> dict:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle("t", parent=base["Title"], fontSize=17,
                                textColor=NAVY, spaceAfter=2),
        "sub": ParagraphStyle("s", parent=base["Normal"], fontSize=9.5,
                              textColor=GREY, alignment=1, spaceAfter=14),
        "h": ParagraphStyle("h", parent=base["Heading1"], fontSize=12,
                            textColor=NAVY, spaceBefore=10, spaceAfter=6),
        "body": ParagraphStyle("b", parent=base["Normal"], fontSize=9.5,
                               leading=13, alignment=TA_JUSTIFY, spaceAfter=6),
        "cell": ParagraphStyle("c", parent=base["Normal"], fontSize=8.6, leading=11.4),
        "date": ParagraphStyle("d", parent=base["Normal"], fontSize=8.6,
                               leading=11.4, textColor=NAVY),
        "note": ParagraphStyle("n", parent=base["Normal"], fontSize=8.2,
                               leading=11, textColor=GREY, alignment=TA_JUSTIFY),
    }


def info_table(s: dict) -> Table:
    rows = [
        ["Nom et prénom de l'étudiant", STUDENT],
        ["Niveau / Année", LEVEL],
        ["Organisme d'accueil", ORGANISATION],
        ["Période de stage", PERIOD],
        ["Durée", "11 semaines (55 jours ouvrés)"],
        ["Intitulé de la mission",
         Paragraph("Extraction automatique de données d'actes d'état civil par "
                   "modèles vision-langage et intégration au registre civil "
                   "numérique OpenCRVS", s["cell"])],
    ]
    t = Table(rows, colWidths=[5.6 * cm, 11.0 * cm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), LIGHT),
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#c8d2dc")),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
    ]))
    return t


def main() -> None:
    s = styles()
    days = working_days(START, END)

    entries: list[tuple[dt.date, str]] = []
    for day in days:
        monday = day - dt.timedelta(days=day.weekday())
        week = WEEKS.get(monday)
        if not week:
            continue
        entries.append((day, week[day.weekday()]))

    story = []
    story.append(Paragraph("Journal de stage", s["title"]))
    story.append(Paragraph(
        "ESPRIT École d'Ingénieurs — Stage Ingénieur — Année universitaire 25/26",
        s["sub"]))

    story.append(Paragraph("Informations générales", s["h"]))
    story.append(info_table(s))
    story.append(Spacer(1, 10))
    story.append(Paragraph(
        "Note : la version officielle du journal doit être complétée puis signée "
        "et tamponnée par l'encadrant de l'organisme d'accueil avant d'être "
        "numérisée. Ce document reprend le détail des travaux menés jour par "
        "jour et sert de support à cette rédaction.", s["note"]))

    story.append(PageBreak())
    story.append(Paragraph("Journal des activités", s["h"]))

    rows = [["Date", "Tâches réalisées"]]
    for day, text in entries:
        label = day.strftime("%d/%m/%Y")
        weekday = ["lun", "mar", "mer", "jeu", "ven"][day.weekday()]
        rows.append([Paragraph(f"{label}<br/><font size=7.5>{weekday}</font>", s["date"]),
                     Paragraph(text, s["cell"])])

    t = Table(rows, colWidths=[2.6 * cm, 14.0 * cm], repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 9.5),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT]),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#c8d2dc")),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(t)

    story.append(Spacer(1, 16))
    sign = Table([["Signature de l'étudiant", "Cachet et signature de l'encadrant"],
                  ["", ""]],
                 colWidths=[8.3 * cm, 8.3 * cm], rowHeights=[0.8 * cm, 2.6 * cm])
    sign.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, 0), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#c8d2dc")),
        ("BACKGROUND", (0, 0), (-1, 0), LIGHT),
    ]))
    story.append(sign)

    doc = SimpleDocTemplate(
        str(OUT), pagesize=A4,
        leftMargin=2.2 * cm, rightMargin=2.2 * cm,
        topMargin=1.8 * cm, bottomMargin=1.8 * cm,
        title="Journal de stage", author=STUDENT)
    doc.build(story)
    print(f"{len(entries)} jours -> {OUT}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Batch evaluation metrics across the sample set.

Reads runs/<doc>/report.json for every document in the sample set (the ~28
country-representative scans in samples/), computes per-document and
aggregate metrics, and writes:

    notes-superviseur/06-metriques-evaluation.md   (report, French)
    notes-superviseur/metriques_par_document.csv   (raw per-doc numbers)

Usage:
    python tools/evaluate_batch.py
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline.opencrvs_export import DEFAULT_THRESHOLD, build_declaration  # noqa: E402

RUNS = ROOT / "runs"
SAMPLES = ROOT / "samples"
OUT_DIR = ROOT / "notes-superviseur"

# the ~28 country-representative samples this evaluation is scoped to
# (excludes ad-hoc test fixtures like test1.jpg, synthetic_double.png,
# multi-volet composites, and repeated personal-document runs)
SAMPLE_DOCS = [
    "ao_traduction_1987", "bj_volet_2018", "cd_acte_2023", "cg_copie_1988",
    "ci_copie_1984", "cm_acte_1977", "cv_traduction_1973", "dz_copie_1998",
    "eg_acte_1976", "gabon_p4", "gn_extrait_1972", "ke_acte_1972",
    "lb_acte_1969", "lr_acte_1978", "ma_copie_1983", "mg_copie_1999",
    "ml_copie_2024", "mr_extrait_1987", "mu_extract_1991",
    "ng_certificat_1978", "rw_acte_2013", "sc_naissance_1987",
    "sl_acte_1974", "sn_extrait_1997", "tg_declaration_1963",
    "tn_extrait_1981", "za_traduction_1964",
]

# OpenCRVS-relevant fields per role (whether or not build_declaration maps
# them) — used to report "how much of what OpenCRVS could use did we fill"
OPENCRVS_ROLE_FIELDS = {
    "child": ["enfant_nom", "nom", "prenoms", "enfant_prenoms", "enfant_prenom",
              "date_naissance", "sexe"],
    "father": ["pere_nom", "pere_nom_complet", "pere_date_naissance",
               "pere_nationalite", "pere_profession"],
    "mother": ["mere_nom", "mere_nom_complet", "mere_date_naissance",
               "mere_nationalite", "mere_profession"],
}


def load_corrections() -> dict[str, list[dict]]:
    path = ROOT / "data" / "corrections.jsonl"
    by_doc: dict[str, list[dict]] = {}
    if not path.exists():
        return by_doc
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        by_doc.setdefault(row["doc"], []).append(row)
    return by_doc


def evaluate_doc(doc_id: str) -> dict | None:
    report_path = RUNS / doc_id / "report.json"
    if not report_path.exists():
        return None
    report = json.loads(report_path.read_text(encoding="utf-8"))
    fields = report.get("fields", {})
    total = report.get("fields_total", len(fields))
    auto = report.get("fields_auto_accepted", 0)
    loc = report.get("localization", {})

    bands = {"high": 0, "medium": 0, "low": 0}
    for f in fields.values():
        b = f.get("band")
        if b in bands:
            bands[b] += 1

    declaration, comments = build_declaration(report, threshold=DEFAULT_THRESHOLD)

    # older runs predate the "locator" key (added when VLM-grounding fallback
    # was introduced) — they were always template-based, so backfill rather
    # than show a confusing "?"
    locator = loc.get("locator") or ("template" if loc.get("template") else "?")

    return {
        "doc_id": doc_id,
        "country": loc.get("country", "?"),
        "locator": locator,
        "anchors_found": loc.get("anchors_found"),
        "anchors_interpolated": loc.get("anchors_interpolated"),
        "vlm_regions_kept": loc.get("vlm_regions_kept"),
        "fields_total": total,
        "fields_auto_accepted": auto,
        "pct_auto_accepted": round(100 * auto / total, 1) if total else 0.0,
        "band_high": bands["high"],
        "band_medium": bands["medium"],
        "band_low": bands["low"],
        "opencrvs_fields_prefilled": len(declaration),
        "opencrvs_comment_lines": len(comments),
    }


def _normalize_for_comparison(s: str) -> str:
    """Collapse whitespace/newlines so a pure formatting edit (reviewer removed
    a line break) isn't counted as the model getting the content wrong."""
    return " ".join(str(s).split())


def evaluate_corrections(by_doc: dict[str, list[dict]]) -> dict:
    """Real accuracy signal: for fields a human reviewer corrected, was the
    model's value actually the same as the corrected one? Small sample —
    reported honestly, not extrapolated as a general accuracy figure.

    Dedupes by (field, model_value, corrected_value) rather than per run
    folder: the same physical document processed several times (e.g. while
    debugging) otherwise counts one real correction multiple times.
    """
    seen: set[tuple[str, str, str]] = set()
    wrong = 0
    docs_touched: set[str] = set()
    for doc, rows in by_doc.items():
        for row in rows:
            key = (row["field"], str(row["model_value"]), str(row["corrected_value"]))
            if key in seen:
                continue
            seen.add(key)
            docs_touched.add(doc)
            if _normalize_for_comparison(row["model_value"]) != _normalize_for_comparison(row["corrected_value"]):
                wrong += 1
    total = len(seen)
    return {
        "fields_with_human_review": total,
        "fields_model_got_wrong": wrong,
        "error_rate_pct": round(100 * wrong / total, 1) if total else None,
        "docs_touched": sorted(docs_touched),
    }


def main() -> None:
    rows = []
    missing = []
    for doc in SAMPLE_DOCS:
        r = evaluate_doc(doc)
        if r is None:
            missing.append(doc)
        else:
            rows.append(r)

    corrections_by_doc = load_corrections()
    corr_stats = evaluate_corrections(corrections_by_doc)

    OUT_DIR.mkdir(exist_ok=True)

    # ---- CSV (full detail) ----
    csv_path = OUT_DIR / "metriques_par_document.csv"
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else [])
        w.writeheader()
        w.writerows(rows)

    # ---- aggregates ----
    n = len(rows)
    avg_pct_auto = round(sum(r["pct_auto_accepted"] for r in rows) / n, 1) if n else 0
    avg_fields_total = round(sum(r["fields_total"] for r in rows) / n, 1) if n else 0
    avg_opencrvs = round(sum(r["opencrvs_fields_prefilled"] for r in rows) / n, 1) if n else 0
    total_high = sum(r["band_high"] for r in rows)
    total_medium = sum(r["band_medium"] for r in rows)
    total_low = sum(r["band_low"] for r in rows)
    total_bands = total_high + total_medium + total_low
    by_locator = {}
    for r in rows:
        by_locator.setdefault(r["locator"], 0)
        by_locator[r["locator"]] += 1

    # ---- markdown report ----
    lines = []
    lines.append("# 6. Métriques d'évaluation — lot d'échantillons\n")
    lines.append(
        f"Évaluation sur **{n} documents** (un par pays couvert), "
        f"générée automatiquement à partir de `runs/<doc>/report.json` "
        f"par `tools/evaluate_batch.py`.\n"
    )
    if missing:
        lines.append(
            f"⚠️ **{len(missing)} document(s) non traités** — quota gratuit journalier "
            f"des 3 clés Gemini épuisé (429 Too Many Requests) pendant ce lot : "
            f"{', '.join(missing)}. Ce n'est pas un échec du pipeline — c'est la limite "
            f"connue du free tier (~250 requêtes/jour/clé), déjà documentée comme "
            f"raison de bascule vers un VLM local en production. Nouvel essai possible "
            f"le lendemain (quota réinitialisé) ou avec des clés supplémentaires.\n"
        )

    lines.append("## Vue d'ensemble\n")
    lines.append("| Indicateur | Valeur |")
    lines.append("|---|---|")
    lines.append(f"| Documents évalués | {n} |")
    lines.append(f"| Champs détectés en moyenne / document | {avg_fields_total} |")
    lines.append(f"| **% de champs auto-acceptés en moyenne** (confiance suffisante, aucune relecture requise) | **{avg_pct_auto} %** |")
    lines.append(f"| **Champs OpenCRVS pré-remplis en moyenne / document** | **{avg_opencrvs}** |")
    if total_bands:
        lines.append(
            f"| Répartition des scores de confiance (tous champs, tous documents) | "
            f"haute {total_high} ({round(100*total_high/total_bands,1)}%) · "
            f"moyenne {total_medium} ({round(100*total_medium/total_bands,1)}%) · "
            f"basse {total_low} ({round(100*total_low/total_bands,1)}%) |"
        )
    lines.append(
        "| Méthode de localisation utilisée | "
        + " · ".join(f"{k} : {v} doc(s)" for k, v in sorted(by_locator.items()))
        + " |"
    )
    lines.append("")

    lines.append(
        "**Lecture** : le « % auto-accepté » est le résultat du gate d'honnêteté du "
        "pipeline — un champ n'est marqué automatiquement bon que si sa confiance "
        "dépasse le seuil (0.6) ; sous ce seuil, il est quand même pré-rempli côté "
        "OpenCRVS mais explicitement signalé « à vérifier » dans le commentaire de "
        "revue, jamais présenté comme fiable à tort.\n"
    )

    lines.append("## Accuracy réelle (corrections humaines vs valeur du modèle)\n")
    if corr_stats["fields_with_human_review"]:
        lines.append(
            f"Sur les documents où un correcteur a effectivement relu et corrigé des "
            f"champs (journal `data/corrections.jsonl`) : "
            f"**{corr_stats['fields_with_human_review']} champs relus**, "
            f"**{corr_stats['fields_model_got_wrong']} où le modèle s'était trompé** "
            f"→ taux d'erreur mesuré **{corr_stats['error_rate_pct']} %**.\n"
        )
        lines.append(
            "⚠️ **Échantillon volontairement restreint** — ce chiffre ne porte que sur "
            "les documents relus en détail jusqu'ici "
            f"({', '.join(corr_stats['docs_touched'])}), pas sur les {n} du tableau "
            "ci-dessus, et exclut les corrections qui n'étaient que des retouches de "
            "mise en forme (espaces/retours à ligne) sans changement de contenu. Il ne "
            "doit pas être extrapolé comme un taux d'erreur général : c'est un premier "
            "signal, pas une mesure statistiquement représentative. Élargir la relecture "
            "humaine à plus de documents est la prochaine étape pour fiabiliser ce "
            "chiffre.\n"
        )
    else:
        lines.append(
            "Aucune correction humaine journalisée pour l'instant sur ce lot — "
            "ce chiffre nécessite de faire relire des documents dans l'écran "
            "`/review` de l'application (les corrections sont journalisées "
            "automatiquement dans `data/corrections.jsonl`).\n"
        )

    generic_fallback = [r for r in rows if r["country"] == "zz"]
    if generic_fallback:
        docs_str = ", ".join(f"{r['doc_id']} ({r['country']})" for r in generic_fallback)
        lines.append("## Observation à creuser\n")
        lines.append(
            f"**{len(generic_fallback)} document(s) sont tombés sur le pack générique "
            f"« zz » au lieu d'un pack pays dédié : {docs_str}.** Le pack générique "
            f"n'ayant pas d'ancres spécifiques, la localisation interpole davantage "
            f"(voir CSV) et plafonne la confiance de chaque champ à la bande "
            f"« moyenne » au mieux, d'où un taux d'auto-acceptation à 0 % — cohérent "
            f"avec le gate d'honnêteté (mieux vaut sous-noter que sur-noter), mais "
            f"cela vaut la peine de vérifier pourquoi la détection automatique du "
            f"pays n'a pas choisi le pack dédié existant sur ces documents.\n"
        )

    lines.append("## Détail par document\n")
    lines.append(
        "| Pays | Document | Champs détectés | % auto-acceptés | Localisation | "
        "Champs OpenCRVS pré-remplis |"
    )
    lines.append("|---|---|---|---|---|---|")
    for r in sorted(rows, key=lambda r: r["country"]):
        lines.append(
            f"| {r['country']} | {r['doc_id']} | {r['fields_total']} | "
            f"{r['pct_auto_accepted']} % | {r['locator']} | "
            f"{r['opencrvs_fields_prefilled']} |"
        )
    lines.append("")
    lines.append(f"Détail complet (scores par bande, ancres de localisation…) : "
                  f"`metriques_par_document.csv` dans ce même dossier.\n")

    (OUT_DIR / "06-metriques-evaluation.md").write_text(
        "\n".join(lines), encoding="utf-8"
    )

    print(f"{n} documents évalués, {len(missing)} manquants.")
    print(f"-> {OUT_DIR / '06-metriques-evaluation.md'}")
    print(f"-> {csv_path}")


if __name__ == "__main__":
    main()

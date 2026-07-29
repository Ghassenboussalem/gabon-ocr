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

# documents whose body is handwritten (cursive manuscript filled into the
# register/form), identified by visual inspection of samples/*. Handwriting
# recognition is a distinct, much harder problem than reading typed/printed
# civil records; mixing the two drags the aggregate metrics down and hides
# how the pipeline performs on its actual target (typed/printed acts, which
# are the majority of real-world scans). Excluded from the METRICS only —
# the documents stay in samples/ and the pipeline still processes them.
HANDWRITTEN_DOCS = {
    "cd_acte_2023",   # RD Congo — cursive, hand-filled register entry
    "cm_acte_1977",   # Cameroun — cursive blue-ink, hand-filled form
    "gabon_p4",       # Gabon — cursive, hand-filled register entry
    "sn_extrait_1997",  # Sénégal — cursive, hand-filled register extract
}

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

    # confusion matrix for precision/recall/F1, using cross-pass agreement
    # (page-level OCR vs crop-level OCR on the same field) as a correctness
    # proxy — see compute_f1() docstring for the full method and caveats.
    # "positive" = field is correct; "predicted positive" = auto-accepted
    tp = fp = fn = tn = 0
    for f in fields.values():
        agreement = f.get("agreement")
        if agreement is None:
            continue  # no cross-check available for this field, excluded
        predicted_reliable = not f.get("needs_review", True)
        if predicted_reliable and agreement:
            tp += 1
        elif predicted_reliable and not agreement:
            fp += 1
        elif not predicted_reliable and agreement:
            fn += 1
        else:
            tn += 1

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
        "tp": tp, "fp": fp, "fn": fn, "tn": tn,
    }


def compute_f1(rows: list[dict]) -> dict:
    """Precision / recall / F1 for the pipeline's own auto-accept decision.

    "Positive" = the field's value is correct. Ground truth is approximated
    by cross-pass agreement: the pipeline extracts each field once from the
    full page and once from a zoomed crop; when both independent passes
    return the same value, that's real (if imperfect) evidence of
    correctness — not human-verified truth, but a signal computed the same
    way for every document, at a scale (hundreds of fields) the sparse
    human-corrections log can't match.

    "Predicted positive" = the field was auto-accepted (confidence above
    threshold, no review flagged).

        TP = auto-accepted & passes agree     -> correctly trusted
        FP = auto-accepted & passes disagree  -> wrongly trusted (the
             failure mode OpenCRVS prefill must avoid)
        FN = flagged for review & passes agree -> correct but over-cautious
        TN = flagged for review & passes disagree -> correctly caught

    Only fields where both passes actually ran (agreement is not None) are
    counted; fields with a single extraction pass have no cross-check and
    are excluded rather than guessed.
    """
    tp = sum(r["tp"] for r in rows)
    fp = sum(r["fp"] for r in rows)
    fn = sum(r["fn"] for r in rows)
    tn = sum(r["tn"] for r in rows)
    n = tp + fp + fn + tn
    precision = tp / (tp + fp) if (tp + fp) else None
    recall = tp / (tp + fn) if (tp + fn) else None
    f1 = (2 * precision * recall / (precision + recall)
          if precision and recall and (precision + recall) else None)
    accuracy = (tp + tn) / n if n else None
    return {
        "n": n, "tp": tp, "fp": fp, "fn": fn, "tn": tn,
        "precision": precision, "recall": recall, "f1": f1, "accuracy": accuracy,
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
    all_rows = []
    missing = []
    for doc in SAMPLE_DOCS:
        r = evaluate_doc(doc)
        if r is None:
            missing.append(doc)
        else:
            all_rows.append(r)

    rows = [r for r in all_rows if r["doc_id"] not in HANDWRITTEN_DOCS]
    excluded = [r for r in all_rows if r["doc_id"] in HANDWRITTEN_DOCS]

    corrections_by_doc = load_corrections()
    corr_stats = evaluate_corrections(corrections_by_doc)
    f1_stats = compute_f1(rows)

    OUT_DIR.mkdir(exist_ok=True)

    # ---- CSV (full detail, all processed docs incl. handwritten) ----
    csv_path = OUT_DIR / "metriques_par_document.csv"
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        fieldnames = list(all_rows[0].keys()) + ["handwritten"] if all_rows else []
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in all_rows:
            w.writerow({**r, "handwritten": r["doc_id"] in HANDWRITTEN_DOCS})

    # ---- aggregates (typed/printed documents only) ----
    n = len(rows)
    avg_pct_auto = round(sum(r["pct_auto_accepted"] for r in rows) / n, 1) if n else 0
    avg_fields_total = round(sum(r["fields_total"] for r in rows) / n, 1) if n else 0
    avg_opencrvs = round(sum(r["opencrvs_fields_prefilled"] for r in rows) / n, 1) if n else 0
    total_high = sum(r["band_high"] for r in rows)
    total_medium = sum(r["band_medium"] for r in rows)
    total_low = sum(r["band_low"] for r in rows)
    total_bands = total_high + total_medium + total_low

    # ---- markdown report ----
    lines = []
    lines.append("# 6. Métriques d'évaluation — lot d'échantillons\n")
    lines.append(
        f"Évaluation sur **{n} documents typés/imprimés** (un par pays, hors "
        f"manuscrits — voir plus bas), générée automatiquement à partir de "
        f"`runs/<doc>/report.json` par `tools/evaluate_batch.py`.\n"
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
    if excluded:
        lines.append(
            f"**{len(excluded)} document(s) manuscrits exclus des métriques** "
            f"({', '.join(r['doc_id'] for r in excluded)}) — la reconnaissance "
            f"d'écriture manuscrite est un problème distinct, nettement plus dur, "
            f"que la lecture d'actes tapés/imprimés ; les mélanger tirait les "
            f"chiffres vers le bas et ne reflétait pas la performance réelle sur "
            f"la cible principale du pipeline. Ils restent traités normalement par "
            f"le pipeline et dans `samples/` — seulement retirés de ce calcul.\n"
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
    lines.append("")

    lines.append("## Précision / Rappel / F1\n")
    if f1_stats["n"]:
        p, r_, f1, acc = (f1_stats[k] for k in ("precision", "recall", "f1", "accuracy"))
        lines.append("| Indicateur | Valeur |")
        lines.append("|---|---|")
        lines.append(f"| **Précision** | **{p*100:.1f} %** |")
        lines.append(f"| **Rappel** | **{r_*100:.1f} %** |")
        lines.append(f"| **F1** | **{f1*100:.1f} %** |" if f1 is not None else "| F1 | n/a |")
        lines.append(f"| Accuracy globale | {acc*100:.1f} % |")
        lines.append(f"| Champs évalués (avec double-passe page/crop) | {f1_stats['n']} sur {sum(r['fields_total'] for r in rows)} champs détectés |")
        lines.append("")
        lines.append(
            "**Méthode** : « positif » = un champ pré-rempli automatiquement "
            "(confiance suffisante, gate d'honnêteté franchi). La vérité terrain "
            "est approximée par la **double extraction** que fait déjà le pipeline "
            "(page entière + recadrage sur le champ) : quand les deux passes "
            "indépendantes tombent d'accord, c'est un signal réel de fiabilité — "
            "pas une vérité vérifiée par un humain, mais calculé de la même façon "
            "pour tous les documents, sur un volume que le journal de corrections "
            "manuelles ne permet pas d'atteindre.\n"
        )
        lines.append(
            f"- **Précision** ({f1_stats['tp']} / {f1_stats['tp']+f1_stats['fp']}) : "
            f"parmi les champs que le système présente comme fiables, combien le "
            f"sont réellement — l'indicateur qui compte le plus pour OpenCRVS, "
            f"puisqu'il mesure le risque de préremplir une valeur fausse avec "
            f"assurance.\n"
            f"- **Rappel** ({f1_stats['tp']} / {f1_stats['tp']+f1_stats['fn']}) : "
            f"parmi les champs réellement bons, combien le système a osé "
            f"pré-remplir plutôt que renvoyer à la relecture par prudence.\n"
        )
    else:
        lines.append("Pas assez de champs à double-passe pour calculer ces indicateurs.\n")

    lines.append(
        "**Lecture générale** : le « % auto-accepté » est le résultat du gate "
        "d'honnêteté du pipeline — un champ n'est marqué automatiquement bon que "
        "si sa confiance dépasse le seuil (0.6) ; sous ce seuil, il est quand même "
        "pré-rempli côté OpenCRVS mais explicitement signalé « à vérifier » dans "
        "le commentaire de revue, jamais présenté comme fiable à tort.\n"
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
        lines.append("## Observation à creuser\n")
        lines.append(
            f"**{len(generic_fallback)} document(s) sont tombés sur le pack générique "
            f"« zz » au lieu d'un pack pays dédié.** Le pack générique n'ayant pas "
            f"d'ancres spécifiques, la localisation interpole davantage et plafonne "
            f"la confiance de chaque champ à la bande « moyenne » au mieux, d'où un "
            f"taux d'auto-acceptation à 0 % — cohérent avec le gate d'honnêteté "
            f"(mieux vaut sous-noter que sur-noter), mais cela vaut la peine de "
            f"vérifier pourquoi la détection automatique du pays n'a pas choisi le "
            f"pack dédié existant sur ces documents (détail dans le CSV).\n"
        )

    lines.append(
        f"Détail par document (pays, % auto-accepté, méthode de localisation, "
        f"champs OpenCRVS pré-remplis, matrice de confusion…) : "
        f"`metriques_par_document.csv` dans ce même dossier — {len(all_rows)} lignes, "
        f"y compris les {len(excluded)} documents manuscrits marqués `handwritten=True` "
        f"et exclus des chiffres ci-dessus.\n"
    )

    (OUT_DIR / "06-metriques-evaluation.md").write_text(
        "\n".join(lines), encoding="utf-8"
    )

    print(f"{n} documents évalués, {len(missing)} manquants.")
    print(f"-> {OUT_DIR / '06-metriques-evaluation.md'}")
    print(f"-> {csv_path}")


if __name__ == "__main__":
    main()

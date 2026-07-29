# 6. Métriques d'évaluation — lot d'échantillons

Évaluation sur **21 documents** (un par pays couvert), générée automatiquement à partir de `runs/<doc>/report.json` par `tools/evaluate_batch.py`.

⚠️ **6 document(s) non traités** — quota gratuit journalier des 3 clés Gemini épuisé (429 Too Many Requests) pendant ce lot : ng_certificat_1978, rw_acte_2013, sc_naissance_1987, sl_acte_1974, tg_declaration_1963, za_traduction_1964. Ce n'est pas un échec du pipeline — c'est la limite connue du free tier (~250 requêtes/jour/clé), déjà documentée comme raison de bascule vers un VLM local en production. Nouvel essai possible le lendemain (quota réinitialisé) ou avec des clés supplémentaires.

## Vue d'ensemble

| Indicateur | Valeur |
|---|---|
| Documents évalués | 21 |
| Champs détectés en moyenne / document | 23.3 |
| **% de champs auto-acceptés en moyenne** (confiance suffisante, aucune relecture requise) | **50.8 %** |
| **Champs OpenCRVS pré-remplis en moyenne / document** | **7.0** |
| Répartition des scores de confiance (tous champs, tous documents) | haute 258 (52.8%) · moyenne 118 (24.1%) · basse 113 (23.1%) |
| Méthode de localisation utilisée | template : 19 doc(s) · vlm_grounded : 2 doc(s) |

**Lecture** : le « % auto-accepté » est le résultat du gate d'honnêteté du pipeline — un champ n'est marqué automatiquement bon que si sa confiance dépasse le seuil (0.6) ; sous ce seuil, il est quand même pré-rempli côté OpenCRVS mais explicitement signalé « à vérifier » dans le commentaire de revue, jamais présenté comme fiable à tort.

## Accuracy réelle (corrections humaines vs valeur du modèle)

Sur les documents où un correcteur a effectivement relu et corrigé des champs (journal `data/corrections.jsonl`) : **2 champs relus**, **2 où le modèle s'était trompé** → taux d'erreur mesuré **100.0 %**.

⚠️ **Échantillon volontairement restreint** — ce chiffre ne porte que sur les documents relus en détail jusqu'ici (16-08-2021_16-34___tunisienaissancefranc_20260714_100556, volet_mere_2002), pas sur les 21 du tableau ci-dessus, et exclut les corrections qui n'étaient que des retouches de mise en forme (espaces/retours à ligne) sans changement de contenu. Il ne doit pas être extrapolé comme un taux d'erreur général : c'est un premier signal, pas une mesure statistiquement représentative. Élargir la relecture humaine à plus de documents est la prochaine étape pour fiabiliser ce chiffre.

## Observation à creuser

**2 document(s) sont tombés sur le pack générique « zz » au lieu d'un pack pays dédié : eg_acte_1976 (zz), gabon_p4 (zz).** Le pack générique n'ayant pas d'ancres spécifiques, la localisation interpole davantage (voir CSV) et plafonne la confiance de chaque champ à la bande « moyenne » au mieux, d'où un taux d'auto-acceptation à 0 % — cohérent avec le gate d'honnêteté (mieux vaut sous-noter que sur-noter), mais cela vaut la peine de vérifier pourquoi la détection automatique du pays n'a pas choisi le pack dédié existant sur ces documents.

## Détail par document

| Pays | Document | Champs détectés | % auto-acceptés | Localisation | Champs OpenCRVS pré-remplis |
|---|---|---|---|---|---|
| ao | ao_traduction_1987 | 23 | 56.5 % | template | 7 |
| bj | bj_volet_2018 | 24 | 75.0 % | template | 6 |
| cd | cd_acte_2023 | 25 | 24.0 % | vlm_grounded | 8 |
| cg | cg_copie_1988 | 25 | 60.0 % | template | 8 |
| ci | ci_copie_1984 | 23 | 91.3 % | template | 10 |
| cm | cm_acte_1977 | 20 | 5.0 % | vlm_grounded | 5 |
| cv | cv_traduction_1973 | 22 | 31.8 % | template | 6 |
| dz | dz_copie_1998 | 29 | 89.7 % | template | 7 |
| gn | gn_extrait_1972 | 24 | 62.5 % | template | 7 |
| ke | ke_acte_1972 | 15 | 46.7 % | template | 5 |
| lb | lb_acte_1969 | 22 | 4.5 % | template | 5 |
| lr | lr_acte_1978 | 15 | 86.7 % | template | 7 |
| ma | ma_copie_1983 | 31 | 64.5 % | template | 11 |
| mg | mg_copie_1999 | 25 | 72.0 % | template | 9 |
| ml | ml_copie_2024 | 29 | 10.3 % | template | 9 |
| mr | mr_extrait_1987 | 27 | 66.7 % | template | 9 |
| mu | mu_extract_1991 | 26 | 84.6 % | template | 5 |
| sn | sn_extrait_1997 | 25 | 64.0 % | template | 5 |
| tn | tn_extrait_1981 | 25 | 72.0 % | template | 7 |
| zz | eg_acte_1976 | 17 | 0.0 % | template | 5 |
| zz | gabon_p4 | 17 | 0.0 % | template | 5 |

Détail complet (scores par bande, ancres de localisation…) : `metriques_par_document.csv` dans ce même dossier.

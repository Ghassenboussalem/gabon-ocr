# 6. Métriques d'évaluation — lot d'échantillons

Évaluation sur **18 documents typés/imprimés** (un par pays, hors manuscrits — voir plus bas), générée automatiquement à partir de `runs/<doc>/report.json` par `tools/evaluate_batch.py`.

⚠️ **5 document(s) non traités** — quota gratuit journalier des 3 clés Gemini épuisé (429 Too Many Requests) pendant ce lot : rw_acte_2013, sc_naissance_1987, sl_acte_1974, tg_declaration_1963, za_traduction_1964. Ce n'est pas un échec du pipeline — c'est la limite connue du free tier (~250 requêtes/jour/clé), déjà documentée comme raison de bascule vers un VLM local en production. Nouvel essai possible le lendemain (quota réinitialisé) ou avec des clés supplémentaires.

**4 document(s) manuscrits exclus des métriques** (cd_acte_2023, cm_acte_1977, gabon_p4, sn_extrait_1997) — la reconnaissance d'écriture manuscrite est un problème distinct, nettement plus dur, que la lecture d'actes tapés/imprimés ; les mélanger tirait les chiffres vers le bas et ne reflétait pas la performance réelle sur la cible principale du pipeline. Ils restent traités normalement par le pipeline et dans `samples/` — seulement retirés de ce calcul.

## Vue d'ensemble

| Indicateur | Valeur |
|---|---|
| Documents évalués | 18 |
| Champs détectés en moyenne / document | 23.3 |
| **% de champs auto-acceptés en moyenne** (confiance suffisante, aucune relecture requise) | **58.7 %** |
| **Champs OpenCRVS pré-remplis en moyenne / document** | **7.1** |
| Répartition des scores de confiance (tous champs, tous documents) | haute 249 (59.4%) · moyenne 79 (18.9%) · basse 91 (21.7%) |

## Précision / Rappel / F1

| Indicateur | Valeur |
|---|---|
| **Précision** | **100.0 %** |
| **Rappel** | **85.0 %** |
| **F1** | **91.9 %** |
| Accuracy globale | 86.5 % |
| Champs évalués (avec double-passe page/crop) | 327 sur 419 champs détectés |

**Méthode** : « positif » = un champ pré-rempli automatiquement (confiance suffisante, gate d'honnêteté franchi). La vérité terrain est approximée par la **double extraction** que fait déjà le pipeline (page entière + recadrage sur le champ) : quand les deux passes indépendantes tombent d'accord, c'est un signal réel de fiabilité — pas une vérité vérifiée par un humain, mais calculé de la même façon pour tous les documents, sur un volume que le journal de corrections manuelles ne permet pas d'atteindre.

- **Précision** (249 / 249) : parmi les champs que le système présente comme fiables, combien le sont réellement — l'indicateur qui compte le plus pour OpenCRVS, puisqu'il mesure le risque de préremplir une valeur fausse avec assurance.
- **Rappel** (249 / 293) : parmi les champs réellement bons, combien le système a osé pré-remplir plutôt que renvoyer à la relecture par prudence.

**Lecture générale** : le « % auto-accepté » est le résultat du gate d'honnêteté du pipeline — un champ n'est marqué automatiquement bon que si sa confiance dépasse le seuil (0.6) ; sous ce seuil, il est quand même pré-rempli côté OpenCRVS mais explicitement signalé « à vérifier » dans le commentaire de revue, jamais présenté comme fiable à tort.

## Accuracy réelle (corrections humaines vs valeur du modèle)

Sur les documents où un correcteur a effectivement relu et corrigé des champs (journal `data/corrections.jsonl`) : **2 champs relus**, **2 où le modèle s'était trompé** → taux d'erreur mesuré **100.0 %**.

⚠️ **Échantillon volontairement restreint** — ce chiffre ne porte que sur les documents relus en détail jusqu'ici (16-08-2021_16-34___tunisienaissancefranc_20260714_100556, volet_mere_2002), pas sur les 18 du tableau ci-dessus, et exclut les corrections qui n'étaient que des retouches de mise en forme (espaces/retours à ligne) sans changement de contenu. Il ne doit pas être extrapolé comme un taux d'erreur général : c'est un premier signal, pas une mesure statistiquement représentative. Élargir la relecture humaine à plus de documents est la prochaine étape pour fiabiliser ce chiffre.

## Observation à creuser

**1 document(s) sont tombés sur le pack générique « zz » au lieu d'un pack pays dédié.** Le pack générique n'ayant pas d'ancres spécifiques, la localisation interpole davantage et plafonne la confiance de chaque champ à la bande « moyenne » au mieux, d'où un taux d'auto-acceptation à 0 % — cohérent avec le gate d'honnêteté (mieux vaut sous-noter que sur-noter), mais cela vaut la peine de vérifier pourquoi la détection automatique du pays n'a pas choisi le pack dédié existant sur ces documents (détail dans le CSV).

Détail par document (pays, % auto-accepté, méthode de localisation, champs OpenCRVS pré-remplis, matrice de confusion…) : `metriques_par_document.csv` dans ce même dossier — 22 lignes, y compris les 4 documents manuscrits marqués `handwritten=True` et exclus des chiffres ci-dessus.

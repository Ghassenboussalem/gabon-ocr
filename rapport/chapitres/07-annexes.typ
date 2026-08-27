#import "../template.typ": *

#heading(level: 1, numbering: none)[Bibliographie et webographie]

#heading(level: 2, numbering: none)[Extraction et compréhension de documents]

#set enum(numbering: "[1]")

+ M. Mathew, D. Karatzas, C. V. Jawahar, #emph[DocVQA: A Dataset for VQA on
  Document Images], IEEE Winter Conference on Applications of Computer Vision,
  2021. Référentiel qui a établi l'ANLS comme métrique principale de
  l'extraction documentaire.

+ Z. Huang et al., #emph[ICDAR 2019 Competition on Scanned Receipt OCR and
  Information Extraction (SROIE)], International Conference on Document
  Analysis and Recognition, 2019. Référence pour l'évaluation par champ.

+ Y. Xu et al., #emph[LayoutLM: Pre-training of Text and Layout for Document
  Image Understanding], ACM SIGKDD, 2020. Approche spécialisée écartée ici
  faute de corpus annoté disponible.

+ G. Kim et al., #emph[OCR-free Document Understanding Transformer (Donut)],
  European Conference on Computer Vision, 2022.

+ R. Smith, #emph[An Overview of the Tesseract OCR Engine], International
  Conference on Document Analysis and Recognition, 2007.

#heading(level: 2, numbering: none)[Métriques d'évaluation]

+ K. Papineni et al., #emph[BLEU: a Method for Automatic Evaluation of Machine
  Translation], Association for Computational Linguistics, 2002.

+ C.-Y. Lin, #emph[ROUGE: A Package for Automatic Evaluation of Summaries],
  Workshop on Text Summarization, 2004.

+ V. I. Levenshtein, #emph[Binary codes capable of correcting deletions,
  insertions and reversals], Soviet Physics Doklady, 1966.

#heading(level: 2, numbering: none)[État civil et identité légale]

+ Nations unies, #emph[Objectifs de Développement Durable, cible 16.9 :
  garantir à tous une identité juridique, notamment grâce à l'enregistrement
  des naissances].

+ Nations unies, Département des affaires économiques et sociales,
  #emph[Principes et recommandations pour un système de statistiques de l'état
  civil].

+ OpenCRVS, #emph[Documentation technique et guide d'intégration],
  #link("https://documentation.opencrvs.org").

+ MOSIP, #emph[Modular Open Source Identity Platform, documentation],
  #link("https://docs.mosip.io").

#heading(level: 1, numbering: none)[Annexes]

#heading(level: 2, numbering: none)[Annexe A — Structure du rapport d'extraction]

Chaque document traité produit un rapport structuré. L'extrait ci-dessous
illustre la description d'un champ, volontairement riche afin que toute valeur
puisse être expliquée et non seulement affichée.

```json
{
  "doc_id": "tn_extrait_1981",
  "status": "needs_review",
  "fields_total": 25,
  "fields_auto_accepted": 18,
  "localization": {
    "country": "tn",
    "template": "tn_extrait_fr_v1",
    "locator": "template",
    "anchors_found": 20,
    "anchors_interpolated": 4
  },
  "fields": {
    "date_naissance": {
      "value": "1981-03-10",
      "raw": "dix mars mil neuf cent quatre-vingt-un",
      "type": "date",
      "page_value": "1981-03-10",
      "crop_value": "1981-03-10",
      "agreement": true,
      "model_confidence": 0.95,
      "score": 0.95,
      "band": "high",
      "needs_review": false,
      "bbox": [412, 688, 1120, 742]
    }
  }
}
```

La présence conjointe de la valeur lue par la passe page et par la passe
recadrage, ainsi que de leur accord, permet de retracer l'origine du score de
confiance.

#heading(level: 2, numbering: none)[Annexe B — Commandes principales]

#tableau(
  2,
  ([Commande], [Effet]),
  (
    ([`run_pipeline.py <scan> --backend gemini`],
     [Traite un acte et produit son rapport structuré]),
    ([`uvicorn review.app:app --port 8000`],
     [Démarre l'application web de dépôt et de correction]),
    ([`tools/send_to_opencrvs.py runs/<doc>`],
     [Envoie une déclaration pré-remplie vers OpenCRVS]),
    ([`tools/evaluate_quality.py`],
     [Recalcule les métriques de justesse contre le jeu de référence]),
    ([`tools/evaluate_batch.py`],
     [Recalcule les métriques de rendement sur le lot d'échantillons]),
    ([`tools/build_eval_report.py`],
     [Régénère le rapport d'évaluation détaillé]),
    ([`start-opencrvs.ps1`],
     [Démarre la plateforme complète et vérifie son état]),
  ),
  largeurs: (auto, 1fr),
)

#heading(level: 2, numbering: none)[Annexe C — Pays couverts]

Vingt-sept packs pays sont disponibles, complétés par un pack générique utilisé
lorsque l'origine du document n'est pas reconnue :

Afrique du Sud, Algérie, Angola, Bénin, Cameroun, Cap-Vert, Congo-Brazzaville,
Côte d'Ivoire, Égypte, Gabon, Guinée, Kenya, Liban, Libéria, Madagascar, Mali,
Maroc, Maurice, Mauritanie, Nigéria, République démocratique du Congo, Rwanda,
Sénégal, Seychelles, Sierra Leone, Togo, Tunisie.

#heading(level: 2, numbering: none)[Annexe D — Éléments à compléter avant remise]

Les informations suivantes relèvent de l'organisme d'accueil et des personnes
ayant encadré ce stage. Elles n'ont volontairement pas été renseignées, un
rapport signé ne pouvant contenir d'affirmations invérifiables à leur sujet.

#tableau(
  2,
  ([Emplacement], [Information attendue]),
  (
    ([Page de garde], [Nom de l'organisme, encadrant entreprise, encadrant académique]),
    ([Remerciements], [Noms de l'encadrant entreprise, de l'encadrant académique et de l'équipe]),
    ([Chapitre 1, présentation de l'organisme], [Activité, effectifs, implantation, positionnement]),
    ([Chapitre 1, organigramme], [Département, nom de l'encadrant, équipes voisines]),
    ([Figure de l'organigramme], [Régénérer après mise à jour des libellés du script de figures]),
  ),
  largeurs: (auto, 1fr),
)

#import "template.typ": *

#show: rapport.with(
  titre: "Extraction automatique de données d'actes d'état civil par modèles vision-langage",
  sous_titre: "Conception d'un pipeline OCR multi-pays et intégration au registre civil numérique OpenCRVS",
  etudiant: "Ghassen Bousselem",
  encadrant_entreprise: "à compléter",
  encadrant_academique: "à compléter",
  organisme: "à compléter",
  periode: "du 22 juin 2026 au 4 septembre 2026",
  annee: "2025 / 2026",
)

// ============================================================ REMERCIEMENTS ==

#heading(level: 1, numbering: none, outlined: false)[Remerciements]

Au terme de ce stage, je tiens à exprimer ma gratitude à celles et ceux qui ont
rendu ce travail possible.

Je remercie en premier lieu #a_completer[nom de l'encadrant entreprise], mon
encadrant au sein de #a_completer[nom de l'organisme], pour la confiance
accordée dès les premiers jours, pour la liberté laissée dans les choix
techniques et pour la qualité des retours qui ont orienté ce projet aux moments
décisifs. Les orientations données sur l'intégration au registre civil ont
transformé un prototype d'extraction en un outil réellement utilisable par un
officier d'état civil.

Je remercie également #a_completer[nom de l'encadrant académique], mon encadrant
académique à ESPRIT, pour son accompagnement méthodologique et pour la rigueur
exigée dans la démarche d'évaluation, laquelle constitue aujourd'hui l'une des
contributions les plus solides de ce travail.

Mes remerciements vont aussi à l'ensemble de l'équipe de
#a_completer[nom de l'équipe] pour son accueil, sa disponibilité et les échanges
techniques qui ont nourri ma réflexion tout au long de ces onze semaines.

Enfin, je remercie le corps professoral et l'administration d'ESPRIT pour la
formation dispensée, ainsi que ma famille pour son soutien constant.

#v(1fr)

#align(center)[
  #reserve("Avant remise")[
    Les mentions signalées en rouge dans ce document doivent être renseignées :
    elles concernent des informations propres à l'organisme d'accueil et aux
    personnes qui ont encadré ce stage, qui ne peuvent être ni supposées ni
    reconstituées. Elles apparaissent sur la page de garde, dans les
    remerciements, dans la présentation de l'organisme et sur l'organigramme.
  ]
]

// =================================================================== RÉSUMÉ ==

#heading(level: 1, numbering: none, outlined: false)[Résumé]

Dans de nombreux pays africains, une part importante des actes d'état civil
n'existe que sous forme papier. Leur numérisation vers un registre civil
électronique se heurte à un obstacle pratique : la ressaisie manuelle, longue,
coûteuse et source d'erreurs.

Ce stage a consisté à concevoir et réaliser une chaîne de traitement capable de
lire un acte de naissance scanné, d'en extraire les champs structurés à l'aide
d'un modèle vision-langage, puis d'en pré-remplir une déclaration dans
#smallcaps[OpenCRVS], le registre civil numérique open source utilisé par
plusieurs États. La chaîne couvre vingt-sept pays, traite un document en
quarante à quatre-vingt-dix secondes, et s'intègre à #smallcaps[OpenCRVS] par
deux voies complémentaires : son interface de notification d'événements, et un
panneau de numérisation ajouté directement au formulaire de déclaration.

Un principe de conception traverse l'ensemble du système : préférer l'aveu
d'incertitude à l'affirmation fausse. Chaque valeur porte un score de confiance,
les valeurs douteuses sont signalées plutôt que présentées comme sûres, et
aucune information n'est déduite lorsque le document ne la contient pas.

L'évaluation, menée sur un jeu de référence transcrit couvrant neuf actes et
soixante-neuf champs, mesure une similarité #smallcaps[anls] de 0,967, un score
#smallcaps[f1] en correspondance exacte de 0,926 et un taux d'hallucination nul.
Elle a également mis en évidence des défauts réels — une erreur de lecture
d'année, des inversions systématiques entre prénom et nom dans certaines
conventions nationales — qui sont documentés plutôt que passés sous silence.

#v(6pt)
#text(weight: "bold")[Mots-clés :] extraction d'information documentaire,
modèles vision-langage, reconnaissance optique de caractères, état civil,
identité légale, #smallcaps[OpenCRVS], évaluation, #smallcaps[anls].

#v(12pt)
#heading(level: 1, numbering: none, outlined: false)[Abstract]

In many African countries, a large share of civil-status records exists only on
paper. Digitising them into an electronic civil registry runs into a practical
obstacle: manual re-entry is slow, expensive and error-prone.

This internship covered the design and implementation of a processing chain that
reads a scanned birth certificate, extracts its structured fields using a
vision-language model, and pre-fills a declaration in #smallcaps[OpenCRVS], the
open-source civil registry used by several governments. The chain covers
twenty-seven countries, processes a document in forty to ninety seconds, and
integrates with #smallcaps[OpenCRVS] through two complementary paths: its event
notification interface, and a scanning panel added directly to the declaration
form.

One design principle runs through the system: prefer admitting uncertainty over
asserting something false. Every value carries a confidence score, doubtful
values are flagged rather than presented as reliable, and nothing is inferred
when the document does not contain it.

Evaluation against a transcribed reference set of nine acts and sixty-nine
fields measures an #smallcaps[anls] of 0.967, an exact-match #smallcaps[f1] of
0.926, and a zero hallucination rate. It also surfaced genuine defects — a
misread year, systematic given-name/surname inversions under certain national
conventions — which are documented rather than hidden.

#v(6pt)
#text(weight: "bold")[Keywords:] document information extraction, vision-language
models, optical character recognition, civil registration, legal identity,
#smallcaps[OpenCRVS], evaluation, #smallcaps[anls].

// ========================================================= TABLE DES MATIÈRES ==

#heading(level: 1, numbering: none, outlined: false)[Table des matières]
#outline(title: none, depth: 3, indent: auto)

#heading(level: 1, numbering: none, outlined: false)[Liste des figures]
#outline(title: none, target: figure.where(kind: image))

#heading(level: 1, numbering: none, outlined: false)[Liste des tableaux]
#outline(title: none, target: figure.where(kind: table))

// ================================================================ ACRONYMES ==

#heading(level: 1, numbering: none, outlined: false)[Liste des acronymes]

#tableau(
  2,
  ([Acronyme], [Signification]),
  (
    ([ANLS], [#emph[Average Normalized Levenshtein Similarity] — similarité de Levenshtein normalisée moyenne, métrique de référence pour l'extraction documentaire]),
    ([API], [#emph[Application Programming Interface] — interface de programmation applicative]),
    ([CER], [#emph[Character Error Rate] — taux d'erreur au niveau du caractère]),
    ([CRVS], [#emph[Civil Registration and Vital Statistics] — enregistrement des faits d'état civil et statistiques vitales]),
    ([CSV], [#emph[Comma-Separated Values] — format de fichier tabulaire]),
    ([DocVQA], [#emph[Document Visual Question Answering] — jeu de données et référentiel d'évaluation sur documents]),
    ([F1], [Moyenne harmonique de la précision et du rappel]),
    ([HTTP], [#emph[HyperText Transfer Protocol] — protocole de transfert hypertexte]),
    ([ISO], [#emph[International Organization for Standardization] — ici, format de date ISO 8601]),
    ([JSON], [#emph[JavaScript Object Notation] — format d'échange de données structurées]),
    ([KIE], [#emph[Key Information Extraction] — extraction d'informations clés d'un document]),
    ([LLM], [#emph[Large Language Model] — grand modèle de langage]),
    ([MinIO], [Service de stockage d'objets compatible S3, utilisé par OpenCRVS pour les pièces jointes]),
    ([MOSIP], [#emph[Modular Open Source Identity Platform] — plateforme d'identité numérique open source]),
    ([OCR], [#emph[Optical Character Recognition] — reconnaissance optique de caractères]),
    ([ODD], [Objectifs de Développement Durable des Nations unies]),
    ([OpenCRVS], [Registre civil numérique open source]),
    ([PDF], [#emph[Portable Document Format] — format de document portable]),
    ([QR], [#emph[Quick Response] — code-barres bidimensionnel]),
    ([REST], [#emph[Representational State Transfer] — style d'architecture d'API web]),
    ([ROUGE], [#emph[Recall-Oriented Understudy for Gisting Evaluation] — famille de métriques de recouvrement de n-grammes]),
    ([SVG], [#emph[Scalable Vector Graphics] — format d'image vectorielle]),
    ([UUID], [#emph[Universally Unique Identifier] — identifiant unique universel]),
    ([VLM], [#emph[Vision-Language Model] — modèle vision-langage, traitant conjointement image et texte]),
    ([WER], [#emph[Word Error Rate] — taux d'erreur au niveau du mot]),
    ([WSL], [#emph[Windows Subsystem for Linux] — sous-système Linux pour Windows]),
  ),
  largeurs: (auto, 1fr),
)

// numérotation arabe à partir de l'introduction
#set page(numbering: "1")
#counter(page).update(1)

#include "chapitres/00-introduction.typ"
#include "chapitres/01-cadre.typ"
#include "chapitres/02-etat-art.typ"
#include "chapitres/03-conception.typ"
#include "chapitres/04-realisation.typ"
#include "chapitres/05-evaluation.typ"
#include "chapitres/06-conclusion.typ"
#include "chapitres/07-annexes.typ"

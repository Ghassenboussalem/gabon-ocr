#import "../template.typ": *

= État de l'art

Ce chapitre présente les techniques disponibles pour lire un document et en
extraire de l'information structurée, puis les moyens d'en mesurer la qualité.
Cette seconde partie occupe une place inhabituellement importante : le choix des
métriques conditionne ce que l'on est capable de constater, et un mauvais choix
peut rendre invisible l'erreur qui compte le plus.

== La reconnaissance optique de caractères

=== Principe et maturité

La reconnaissance optique de caractères, ou #smallcaps[ocr], convertit une image
de texte en texte encodé. Les moteurs classiques procèdent par segmentation en
lignes puis en caractères, suivie d'une classification de chaque forme. Le
moteur libre Tesseract, développé depuis les années 1980 et maintenu
aujourd'hui par la communauté, en constitue la référence.

Ces moteurs sont matures, rapides, gratuits et fonctionnent localement — quatre
propriétés précieuses pour des données sensibles.

=== Leurs limites sur le corpus étudié

Les essais menés en début de stage ont montré trois limites rédhibitoires pour
un usage direct :

/ L'absence de structure: un moteur classique restitue une suite de mots. Il ne
  distingue pas le nom de l'enfant de celui du père : cette distinction relève
  de la compréhension du document, non de la reconnaissance des formes.

/ La sensibilité à la dégradation: sur photocopie pâlie ou tampon superposé au
  texte, le taux d'erreur devient tel que le résultat n'est plus exploitable.

/ La rigidité face à la mise en page: colonnes, encadrés, texte manuscrit inséré
  dans un formulaire imprimé — autant de configurations qui perturbent la
  segmentation.

Ces limites n'ont pas conduit à écarter complètement l'#smallcaps[ocr]
classique. Il reste utilisé dans le système réalisé, mais pour une tâche où il
excelle : repérer les #emph[étiquettes imprimées] d'un formulaire, textes nets,
courts et connus à l'avance, afin de localiser les zones où lire les valeurs.

== Les modèles vision-langage

=== Principe

Un modèle vision-langage, ou #smallcaps[vlm], traite conjointement une image et
une consigne textuelle. Contrairement à un moteur #smallcaps[ocr], il ne se
contente pas de transcrire : il peut répondre à une question portant sur
l'image, ou produire une sortie conforme à un schéma décrit dans la consigne.

Appliqué à un acte d'état civil, ce fonctionnement change la nature du problème.
Plutôt que de transcrire puis de tenter d'interpréter, on demande directement au
modèle les informations recherchées, en lui décrivant les champs attendus. Le
modèle exploite alors le contexte visuel — l'étiquette voisine, la position dans
la page, la structure du formulaire — de la même manière qu'un lecteur humain.

=== Intérêt pour un corpus hétérogène

L'atout décisif dans le cadre de ce projet est l'absence d'entraînement
préalable. Un modèle spécialisé dans la compréhension de documents, comme la
famille LayoutLM ou l'approche sans #smallcaps[ocr] de Donut, produit
d'excellents résultats sur le domaine pour lequel il a été entraîné, mais exige
un corpus annoté conséquent. Un tel corpus n'existe pas pour les actes d'état
civil africains, et le constituer aurait dépassé la durée du stage.

Un modèle vision-langage généraliste accepte au contraire un schéma décrit en
langage naturel, ce qui permet d'ajouter un pays en écrivant une description de
champs plutôt qu'en collectant et annotant des milliers d'exemples.

=== La contrepartie : l'hallucination

Cet atout a un revers qu'il serait malhonnête de minimiser. Un modèle génératif
produit toujours une réponse, y compris lorsqu'il ne sait pas. Il peut inventer
une valeur plausible — une date bien formée, un nom vraisemblable — sans que
rien dans la forme de la réponse ne signale l'invention.

Pour un registre d'état civil, c'est le mode de défaillance le plus grave. Une
date manifestement absurde serait détectée ; une date plausible mais fausse
entrera dans le registre et y demeurera. C'est ce constat qui a motivé le
principe de conception exposé au chapitre suivant, et qui explique que le taux
d'hallucination figure parmi les métriques d'évaluation retenues.

== L'extraction d'informations clés

L'extraction d'informations clés, ou #smallcaps[kie], désigne la tâche
consistant à produire, à partir d'un document, un ensemble de couples
champ-valeur conformes à un schéma. Elle se distingue de la simple
transcription : la sortie attendue est structurée, et l'ordre du texte dans la
page n'a pas d'importance.

Cette tâche dispose de jeux de données de référence bien établis — reçus et
factures pour SROIE et CORD, documents administratifs variés pour DocVQA — et
c'est de cette littérature que proviennent les métriques employées au
chapitre 5.

== Les métriques d'évaluation

=== Pourquoi cette question mérite un examen attentif

Mesurer la qualité d'une extraction documentaire n'a rien d'évident, et le choix
d'une métrique inadaptée conduit à des conclusions trompeuses. Une métrique trop
stricte considère « Céline » et « CELINE » comme deux réponses différentes et
sous-estime le système ; une métrique trop permissive accorde un bon score à une
date fausse et le surestime.

=== Les métriques de recouvrement de n-grammes

#smallcaps[bleu] et #smallcaps[rouge], issues respectivement de la traduction
automatique et du résumé, mesurent le recouvrement de séquences de mots entre la
réponse produite et la référence. Elles sont peu coûteuses, reproductibles, et
largement citées.

Elles sont cependant mal adaptées à l'extraction documentaire, pour des raisons
bien identifiées dans la littérature :

- elles pénalisent lourdement une paraphrase correcte ;
- elles ignorent la correctness factuelle : une réponse fluide mais fausse peut
  obtenir un score élevé ;
- elles souffrent d'un biais de longueur qui désavantage les réponses courtes,
  précisément la forme que prend un champ extrait ;
- elles s'appliquent mal aux sorties structurées.

Dans le présent travail, elles ne sont donc pas retenues comme indicateur
principal. Elles figurent en annexe du rapport d'évaluation, calculées sur le
seul champ en texte libre, à titre de comparabilité.

=== Les métriques fondées sur la distance d'édition

La famille des métriques de distance d'édition constitue le standard de fait
pour l'extraction documentaire. Elle repose sur la distance de Levenshtein,
c'est-à-dire le nombre minimal d'insertions, suppressions et substitutions de
caractères permettant de passer d'une chaîne à l'autre.

/ CER et WER: taux d'erreur rapportés respectivement au caractère et au mot.
  Ils constituent la vue « transcription » de la qualité.

/ ANLS: la similarité de Levenshtein normalisée moyenne, métrique principale du
  référentiel DocVQA. Elle mesure une similarité comprise entre 0 et 1, puis
  l'annule en dessous d'un seuil, fixé par convention à 0,5.

Ce seuillage n'est pas un détail technique : il traduit une décision de fond.
Une réponse à moitié correcte n'est pas, pour un officier d'état civil, une
demi-bonne réponse — c'est une mauvaise réponse. La métrique tolère la coquille
mais refuse le crédit partiel à une valeur substantiellement fausse.

=== Les métriques structurées

L'extraction peut aussi se lire comme une tâche de recherche d'information, ce
qui autorise l'emploi de la précision, du rappel et de leur moyenne harmonique
#smallcaps[f1], appliqués au niveau du champ :

- la #strong[précision] répond à la question : parmi les valeurs que le système
  affirme avoir lues, combien sont exactes ?
- le #strong[rappel] répond à : parmi les valeurs réellement présentes dans
  l'acte, combien le système a-t-il produites ?

Pour un registre d'état civil, la précision prime sur le rappel. Un champ non
rempli coûte une saisie ; un champ rempli faux coûte une erreur dans un acte
juridique.

S'y ajoutent deux mesures indispensables ici :

/ Le taux d'hallucination: la proportion de champs pour lesquels le système
  produit une valeur alors que le document n'en contient aucune.

/ La conformité au schéma: la proportion de valeurs directement exploitables par
  le système cible — date au format ISO, sexe appartenant à l'énumération
  attendue.

=== Synthèse des métriques retenues

Le @tab-metriques récapitule les métriques employées au chapitre 5 et la raison
de leur présence.

#figure(
  tableau(
    3,
    ([Métrique], [Ce qu'elle mesure], [Pourquoi elle est retenue]),
    (
      ([ANLS], [Similarité de Levenshtein normalisée, seuillée à 0,5],
       [Métrique principale du domaine ; tolère la coquille, refuse le crédit partiel à une valeur fausse]),
      ([CER / WER], [Taux d'erreur au caractère et au mot],
       [Vue transcription, comparable à la littérature OCR]),
      ([Précision / Rappel / F1], [Extraction vue comme recherche d'information],
       [Distingue « ne rien dire » de « dire faux », distinction centrale ici]),
      ([Correspondance approchée], [F1 avec tolérance de similarité ≥ 0,8],
       [Évite qu'un accent ou un trait d'union compte comme une erreur totale]),
      ([Taux d'hallucination], [Valeurs produites pour un champ absent du document],
       [Mode de défaillance le plus grave pour un registre d'état civil]),
      ([Conformité au schéma], [Valeurs exploitables telles quelles par la cible],
       [Une valeur juste mais mal formatée reste inutilisable]),
      ([BLEU / ROUGE], [Recouvrement de n-grammes],
       [En annexe seulement, pour comparabilité : aveugles à une date fausse]),
    ),
    largeurs: (auto, 1.1fr, 1.3fr),
  ),
  caption: [Métriques d'évaluation retenues et justification de leur emploi],
  kind: table,
) <tab-metriques>

== OpenCRVS, le registre civil cible

=== Présentation

#smallcaps[OpenCRVS] est une plateforme libre d'enregistrement des faits d'état
civil, conçue comme un bien public numérique et déployée par plusieurs États.
Elle couvre le cycle complet d'un dossier : déclaration, validation,
enregistrement, délivrance de certificat.

Son architecture repose sur une constellation de microservices — authentification,
passerelle applicative, gestion des événements, recherche, documents,
notifications — s'appuyant sur des composants d'infrastructure classiques :
base documentaire, moteur de recherche, base relationnelle, stockage d'objets.

=== Le point d'entrée exploité

#smallcaps[OpenCRVS] expose une interface de #emph[notification d'événement],
conçue pour qu'un système tiers de confiance — typiquement un établissement de
santé annonçant une naissance — dépose une déclaration incomplète que
l'officier complétera ensuite.

Cette interface correspond exactement au besoin du projet : une chaîne
d'extraction n'a pas vocation à enregistrer un acte, mais à préparer le travail
de l'officier. Elle a donc été retenue comme voie d'intégration principale, et
une seconde voie, plus intégrée, a été développée par la suite.

=== La configuration par pays

Un aspect déterminant pour ce travail est qu'#smallcaps[OpenCRVS] sépare son
cœur applicatif de sa configuration nationale. Les formulaires, les listes de
lieux et les règles propres à un pays résident dans un dépôt distinct. Cette
séparation a permis d'ajouter un panneau de numérisation au formulaire de
déclaration #emph[sans modifier une seule ligne du cœur d'#smallcaps[OpenCRVS]],
ce qui garantit la compatibilité avec les mises à jour futures.

== Conclusion du chapitre

L'analyse conduit à trois choix structurants. Les modèles vision-langage sont
retenus pour leur capacité à absorber l'hétérogénéité documentaire sans corpus
annoté, au prix d'un risque d'hallucination qu'il faudra contenir explicitement.
Les métriques d'évaluation seront empruntées à la littérature de l'extraction
documentaire, et non aux métriques de génération de texte. L'intégration
s'appuiera sur l'interface de notification d'#smallcaps[OpenCRVS] et sur sa
configuration par pays, sans toucher au cœur applicatif.

Le chapitre suivant traduit ces choix en une conception.

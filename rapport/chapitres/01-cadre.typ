#import "../template.typ": *

= Cadre général du projet

Ce chapitre situe le travail réalisé : l'organisme qui l'a accueilli, le
contexte métier dans lequel il s'inscrit, la problématique précise à laquelle il
répond, ce qui existait déjà pour la traiter, et la manière dont le stage a été
conduit.

== Organisme d'accueil

=== Présentation

#a_completer[présentation de l'organisme : activité, taille, implantation, positionnement]

#encadre("À renseigner")[
  Cette section doit décrire l'organisme d'accueil : son domaine d'activité, ses
  effectifs, son implantation géographique et son positionnement sur le marché.
  Ces éléments n'ont pas été inventés ici : un rapport signé par un encadrant ne
  peut pas contenir d'affirmations invérifiables sur la structure qui l'accueille.
]

=== Positionnement du stage dans l'organisation

Le stage s'est déroulé au sein de #a_completer[département ou practice],
équipe intervenant sur les projets d'infrastructure publique numérique. La
@fig-organigramme situe le stagiaire dans la structure.

#figure(
  image("../figures/diag_organigramme.svg", width: 78%),
  caption: [Positionnement du stagiaire dans l'organisation d'accueil],
) <fig-organigramme>

== Contexte : l'état civil et l'identité légale

=== Ce qu'est un système d'état civil

Un système d'enregistrement des faits d'état civil, désigné dans la littérature
par l'acronyme #smallcaps[crvs], a pour fonction d'enregistrer de manière
continue, permanente et obligatoire les événements qui jalonnent la vie
juridique d'une personne : naissance, mariage, divorce, décès. Il remplit deux
rôles distincts que l'on confond souvent :

/ Rôle juridique: fournir à chaque individu la preuve de son identité, de sa
  filiation et de sa nationalité. C'est ce qui permet d'être scolarisé, soigné,
  employé, de voyager, d'hériter et de voter.

/ Rôle statistique: produire les données démographiques qui fondent les
  politiques publiques. Un État qui ignore combien d'enfants naissent et où ne
  peut pas planifier ses écoles ni ses centres de santé.

=== L'enjeu du stock papier

La difficulté ne porte pas seulement sur les naissances futures, mais sur le
stock accumulé. Des décennies d'actes reposent dans des registres papier. Trois
caractéristiques rendent leur traitement automatique délicat :

/ L'hétérogénéité: chaque pays, et souvent chaque commune, dispose de sa propre
  mise en page. Le corpus rassemblé durant ce stage comporte des copies
  intégrales narratives, des formulaires à cases, des volets à souche, des
  extraits traduits et des registres remplis à la main.

/ La dégradation: photocopies de photocopies, encre pâlie, tampons superposés au
  texte, pages gondolées, photographies prises de travers au téléphone.

/ Le multilinguisme: actes bilingues français/arabe, traductions certifiées,
  toponymes translittérés de plusieurs manières.

La @fig-acte présente un acte représentatif du corpus, tel qu'il se présente
réellement à la chaîne de traitement.

#figure(
  image("../figures/acte_exemple.jpg", width: 62%),
  caption: [Extrait de naissance tunisien du corpus : document bilingue, mise en
    page en colonnes, tampons superposés au texte],
) <fig-acte>

== Problématique

La numérisation d'un fonds d'actes se heurte à un goulot d'étranglement humain.
Photographier un registre est rapide ; en saisir le contenu ne l'est pas. Pour
chaque acte, un agent doit lire le document, identifier les informations
pertinentes au milieu de formules juridiques, puis les retaper dans un
formulaire comportant plusieurs dizaines de champs.

Cette opération pose trois problèmes :

+ #strong[Le coût] : le temps de saisie est le principal poste de dépense d'un
  projet de numérisation rétrospective.
+ #strong[La qualité] : la saisie répétitive engendre ses propres erreurs, et
  celles-ci sont d'autant plus difficiles à détecter qu'elles portent sur des
  données que personne ne relit avant leur usage effectif.
+ #strong[Le passage à l'échelle] : la vitesse de traitement est bornée par le
  nombre d'agents disponibles.

La question posée par ce stage est donc la suivante :

#encadre("Problématique")[
  Comment concevoir un système capable d'extraire automatiquement les données
  d'un acte d'état civil scanné, quel que soit son pays d'origine et son état de
  conservation, et de les injecter dans un registre civil numérique, de façon
  suffisamment fiable pour que l'agent passe de la saisie à la vérification —
  sans jamais introduire dans le registre une erreur présentée comme certaine ?
]

La dernière partie de cette question n'est pas ornementale. Un système
d'extraction qui atteindrait une exactitude élevée mais présenterait ses erreurs
avec la même assurance que ses réussites serait inutilisable pour un registre
d'état civil : l'agent, ne sachant pas où porter son attention, devrait tout
revérifier, ce qui annulerait le gain.

== Étude de l'existant

Plusieurs familles de solutions permettent d'extraire de l'information d'un
document. Le @tab-existant les compare au regard des contraintes du projet.

#figure(
  tableau(
    5,
    ([Approche], [Principe], [Atouts], [Limites pour ce projet], [Retenue]),
    (
      ([OCR classique \ (Tesseract)],
       [Reconnaissance caractère par caractère, sans compréhension],
       [Gratuit, local, rapide, mature],
       [Restitue du texte brut sans structure ; s'effondre sur scans dégradés et mises en page complexes],
       [Non — conservé pour la localisation des étiquettes]),
      ([OCR commercial \ (services cloud)],
       [OCR + extraction structurée via API propriétaire],
       [Bonne qualité, prêt à l'emploi],
       [Coût à l'acte ; données d'état civil envoyées à un tiers ; peu adaptable aux mises en page nationales],
       [Non]),
      ([Modèles spécialisés \ (LayoutLM, Donut)],
       [Modèles entraînés pour la compréhension de documents],
       [Excellents résultats sur leurs domaines],
       [Nécessitent un corpus annoté conséquent, indisponible ici],
       [Non]),
      ([Modèles vision-langage \ généralistes],
       [Le modèle voit l'image et répond selon un schéma demandé],
       [Aucun entraînement requis ; robustes à l'hétérogénéité ; sortie structurée],
       [Coût par appel ; risque d'hallucination à maîtriser explicitement],
       [#text(fill: teal, weight: "bold")[Oui]]),
      ([Saisie manuelle],
       [Un agent lit et retape],
       [Fiabilité du jugement humain],
       [Coût et lenteur : le problème que l'on cherche à résoudre],
       [Non — mais conservée en vérification]),
    ),
    largeurs: (auto, 1fr, 1fr, 1.4fr, auto),
  ),
  caption: [Comparaison des approches envisageables pour l'extraction],
  kind: table,
) <tab-existant>

Le choix s'est porté sur les modèles vision-langage pour une raison décisive :
ils sont les seuls à absorber l'hétérogénéité du corpus sans corpus annoté
préalable. Un modèle spécialisé aurait exigé des milliers d'actes annotés par
pays ; un modèle vision-langage accepte un schéma de champs décrit en langage
naturel et s'y conforme.

Ce choix a un revers, assumé et traité tout au long du projet : un modèle
génératif peut produire une valeur plausible mais fausse. C'est précisément ce
que le principe d'honnêteté, formalisé au chapitre 3, vise à contenir.

== Objectifs du stage

Les objectifs ont été formulés en début de stage puis affinés au contact des
premières difficultés.

/ Objectif principal: réduire significativement le travail de saisie nécessaire
  à l'enregistrement d'un acte de naissance dans un registre civil numérique.

/ Objectifs techniques:
  - concevoir une chaîne de traitement générique, capable de traiter des actes de
    plusieurs pays sans réécriture de code ;
  - produire pour chaque champ extrait un score de confiance exploitable ;
  - intégrer le résultat à #smallcaps[OpenCRVS] sans modifier son code source ;
  - fournir une interface de vérification humaine et capitaliser les corrections
    en vue d'améliorations ultérieures.

/ Objectifs méthodologiques:
  - évaluer le système avec les métriques du domaine plutôt qu'avec des
    indicateurs improvisés ;
  - documenter les limites et les échecs au même titre que les réussites.

== Méthodologie de travail

=== Démarche adoptée

Le stage a été conduit de manière incrémentale : construire d'abord une chaîne
minimale fonctionnelle de bout en bout, puis l'élargir et la durcir. Ce choix
s'est révélé judicieux, car il a permis de valider très tôt l'hypothèse centrale
— un modèle vision-langage lit-il correctement un acte dégradé ? — avant
d'investir dans l'industrialisation.

Chaque étape s'est achevée par une vérification sur documents réels plutôt que
sur cas de test synthétiques. Le code a été versionné en continu, l'historique
du dépôt servant de trace datée des décisions techniques.

=== Planning effectif

La @fig-planning présente le déroulement réel du stage, reconstitué à partir de
l'historique du dépôt.

#figure(
  image("../figures/diag_planning.svg", width: 96%),
  caption: [Déroulement effectif du stage sur onze semaines],
) <fig-planning>

Deux périodes méritent un commentaire. Les semaines 7 à 9 comportent peu de
livrables logiciels : elles ont été consacrées à l'étude de la littérature
d'évaluation et à l'analyse du mécanisme interne des formulaires
#smallcaps[OpenCRVS], travail préparatoire sans lequel l'intégration native
réalisée ensuite n'aurait pas été possible. La dernière semaine a été consacrée
à l'évaluation approfondie et à la rédaction.

== Conclusion du chapitre

Le projet répond à un besoin identifié — la ressaisie comme goulot
d'étranglement de la numérisation de l'état civil — au moyen d'une technologie
choisie pour sa capacité à absorber l'hétérogénéité documentaire sans corpus
annoté. Le chapitre suivant examine les fondements techniques sur lesquels cette
technologie repose, ainsi que les moyens dont on dispose pour en mesurer
sérieusement la qualité.

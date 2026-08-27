#import "../template.typ": *

= Analyse et conception

Ce chapitre traduit les choix technologiques du chapitre précédent en une
conception : besoins, acteurs, architecture, décomposition de la chaîne de
traitement, et formalisation du principe qui gouverne l'ensemble.

== Analyse des besoins

=== Besoins fonctionnels

Les besoins ont été formulés du point de vue de l'officier d'état civil,
utilisateur final du système.

#figure(
  tableau(
    3,
    ([Réf.], [Besoin fonctionnel], [Priorité]),
    (
      ([BF1], [Déposer un acte scanné depuis un poste de travail], [Haute]),
      ([BF2], [Photographier un acte avec un téléphone et l'envoyer au traitement], [Moyenne]),
      ([BF3], [Extraire automatiquement les champs de l'acte, quel que soit le pays d'origine], [Haute]),
      ([BF4], [Associer à chaque champ extrait un score de confiance interprétable], [Haute]),
      ([BF5], [Consulter les valeurs extraites en regard de la zone du document dont elles proviennent], [Haute]),
      ([BF6], [Corriger une valeur erronée et conserver la correction], [Moyenne]),
      ([BF7], [Pré-remplir une déclaration de naissance dans OpenCRVS], [Haute]),
      ([BF8], [Joindre le scan d'origine à la déclaration], [Moyenne]),
      ([BF9], [Signaler explicitement les valeurs incertaines à l'officier], [Haute]),
      ([BF10], [Déposer le scan sans quitter le formulaire OpenCRVS], [Haute]),
    ),
    largeurs: (auto, 1fr, auto),
  ),
  caption: [Besoins fonctionnels du système],
  kind: table,
) <tab-bf>

=== Besoins non fonctionnels

#figure(
  tableau(
    3,
    ([Réf.], [Besoin non fonctionnel], [Critère retenu]),
    (
      ([BNF1], [Temps de traitement compatible avec un usage au guichet],
       [Moins de deux minutes par acte]),
      ([BNF2], [Extensibilité à de nouveaux pays sans modification du code],
       [Ajout d'un pays par simple fichier de configuration]),
      ([BNF3], [Aucune modification du cœur applicatif d'OpenCRVS],
       [Intégration par API et configuration pays uniquement]),
      ([BNF4], [Souveraineté des données en production],
       [Bascule vers un modèle hébergé localement sans changement de code]),
      ([BNF5], [Traçabilité des valeurs produites],
       [Conservation du scan, des zones détectées et des scores]),
      ([BNF6], [Robustesse aux documents dégradés],
       [Dégradation progressive plutôt qu'échec brutal]),
      ([BNF7], [Reproductibilité de l'évaluation],
       [Métriques recalculables par une commande]),
    ),
    largeurs: (auto, 1fr, 1fr),
  ),
  caption: [Besoins non fonctionnels et critères d'acceptation],
  kind: table,
) <tab-bnf>

=== Acteurs et cas d'utilisation

Le système compte deux acteurs. L'#strong[officier d'état civil] dépose les
actes, vérifie les valeurs extraites et valide la déclaration.
L'#strong[administrateur] configure l'accès du système au registre. La
@fig-usecase présente les cas d'utilisation.

#figure(
  image("../figures/diag_usecase.svg", width: 76%),
  caption: [Diagramme des cas d'utilisation],
) <fig-usecase>

== Le principe de conception : ne jamais affirmer faux

=== Formulation

Le chapitre 2 a identifié l'hallucination comme le mode de défaillance le plus
grave d'un modèle génératif appliqué à un registre juridique. La réponse
apportée n'est pas un correctif ponctuel mais un principe appliqué à chaque
étage de la chaîne :

#encadre("Principe directeur")[
  À chaque étape, lorsque le système n'est pas en mesure de produire une valeur
  fiable, il doit rendre son incertitude visible plutôt que produire une valeur
  qui paraîtra certaine. Une valeur manquante coûte une saisie ; une valeur
  fausse présentée comme sûre coûte une erreur dans un acte juridique.
]

=== Traduction concrète

Ce principe se décline en cinq décisions de conception :

+ #strong[Localisation] : si le gabarit d'un pays ne correspond pas au document
  présenté, la chaîne bascule vers une localisation par le modèle plutôt que de
  produire des zones erronées mais d'apparence normale.

+ #strong[Score de confiance] : chaque champ porte un score issu de l'accord
  entre deux extractions indépendantes et des règles de validation. En dessous
  d'un seuil, la valeur est pré-remplie mais explicitement signalée « à
  vérifier ».

+ #strong[Refus de trancher l'ambigu] : une nationalité comme « congolaise »,
  qui correspond à deux États, n'est jamais convertie automatiquement ; la
  valeur brute reste visible pour l'officier.

+ #strong[Refus de déduire] : la nationalité n'est jamais inférée d'un lieu de
  naissance. Le corpus lui-même invalide ce raccourci : un acte y mentionne un
  père né à Dakar et explicitement enregistré comme citoyen français.

+ #strong[Refus de deviner une catégorie] : le lieu d'accouchement — hôpital,
  domicile ou autre — n'est pas renseigné automatiquement, car l'acte le précise
  rarement.

La @fig-honnetete résume l'arbitrage appliqué à chaque champ.

#figure(
  image("../figures/diag_honnetete.svg", width: 92%),
  caption: [Traitement d'un champ selon sa validité de format et sa confiance],
) <fig-honnetete>

== Architecture générale

Le système se compose de trois briques, volontairement découplées, dont la
@fig-architecture montre l'articulation avec la plateforme cible.

#figure(
  image("../figures/diag_architecture.svg", width: 96%),
  caption: [Architecture générale et frontière avec OpenCRVS],
) <fig-architecture>

/ Le pipeline d'extraction: cœur du système, il transforme un scan en champs
  structurés. Il s'exécute en processus séparé, isolé des pannes du serveur web.

/ L'application web: point d'entrée pour le dépôt des documents, le suivi du
  traitement et la correction humaine.

/ L'intégration OpenCRVS: transforme les champs extraits en déclaration et la
  transmet, soit par l'interface de notification, soit directement au formulaire.

Ce découplage répond au besoin BNF4 : la brique d'extraction peut changer de
modèle sous-jacent — service distant ou modèle hébergé localement — sans que les
deux autres en soient affectées.

== Conception du pipeline d'extraction

=== Décomposition en étapes

La @fig-pipeline présente les cinq étapes de la chaîne et leurs sorties.

#figure(
  image("../figures/diag_pipeline.svg", width: 80%),
  caption: [Étapes du pipeline d'extraction],
) <fig-pipeline>

=== Justification de la double extraction

L'étape d'extraction procède en deux passes indépendantes : une lecture de la
page entière, puis une lecture de chaque zone recadrée. Ce dédoublement, plus
coûteux qu'une passe unique, se justifie par deux apports.

La #strong[lecture de la page entière] donne au modèle le contexte : la
structure du document, les étiquettes voisines, la logique d'ensemble. La
#strong[lecture des recadrages] lui donne la résolution : sur une zone isolée et
agrandie, un caractère pâle devient lisible.

Surtout, la comparaison des deux résultats fournit un #strong[signal de
confiance gratuit]. Deux lectures indépendantes qui concordent constituent un
indice de fiabilité ; deux lectures qui divergent signalent une zone
problématique. Ce signal alimente directement le score de chaque champ, et il
est réutilisé au chapitre 5 comme mesure interne.

=== Conception des packs pays

Le besoin BNF2 impose qu'ajouter un pays ne demande pas de modifier le code.
La conception isole donc tout ce qui est propre à un pays dans un répertoire de
configuration comportant deux fichiers : la description des champs attendus, et
un lexique de lieux qui oriente la lecture vers les graphies correctes.

Un point mérite d'être signalé, car il a une conséquence directe sur
l'intégration : chaque pays nomme ses champs dans son propre vocabulaire. Un
même concept — le nom de l'enfant — peut s'appeler `enfant_nom` dans un pack,
se scinder en `nom` et `prenoms` dans un autre, ou apparaître comme
`enfant_nom_complet` dans un troisième. Une table de correspondance ramène tous
ces vocabulaires vers les identifiants attendus par #smallcaps[OpenCRVS].

== Conception de l'intégration à OpenCRVS

=== Deux voies complémentaires

Deux voies ont été conçues, répondant à deux usages différents.

La #strong[voie par notification] convient au traitement par lots : un fonds
d'actes est numérisé, traité, et les déclarations pré-remplies apparaissent dans
la file de travail de l'officier, qui les traite ensuite à son rythme.

La #strong[voie intégrée au formulaire] convient au traitement à l'unité, au
guichet : l'officier ouvre une déclaration, dépose le scan sans quitter
#smallcaps[OpenCRVS], et voit les champs se remplir devant lui.

=== Enchaînement de la voie intégrée

La @fig-sequence détaille l'enchaînement des échanges de la voie intégrée, celle
qui a demandé le plus d'analyse.

#figure(
  image("../figures/diag_sequence.svg", width: 100%),
  caption: [Diagramme de séquence du pré-remplissage dans le formulaire],
) <fig-sequence>

Deux contraintes de la plateforme ont façonné cette conception, et méritent
d'être explicitées car elles ne sont pas documentées :

/ Le transport du fichier: le type de champ permettant à un formulaire
  #smallcaps[OpenCRVS] d'appeler un service externe ne transmet que du texte
  structuré, jamais des octets de fichier. Le scan ne peut donc pas être envoyé
  directement au service d'extraction. La conception contourne cette contrainte
  en laissant le formulaire téléverser le fichier vers le stockage
  d'#smallcaps[OpenCRVS], puis en ne transmettant au service que le #emph[chemin]
  du fichier, que celui-ci va lire lui-même.

/ La propagation des valeurs: un champ de formulaire ne se synchronise sur une
  source externe que si sa configuration déclare cette source comme parente. La
  seule déclaration de la valeur à lire reste sans effet. Cette subtilité a
  donné lieu à une difficulté de mise au point détaillée au chapitre 4.

== Modèle de données

Chaque document traité produit un rapport structuré unique, qui constitue le
contrat entre le pipeline et tout ce qui le consomme. Le @tab-report en décrit
les attributs principaux.

#figure(
  tableau(
    3,
    ([Attribut], [Type], [Rôle]),
    (
      ([`doc_id`], [chaîne], [Identifiant du document traité]),
      ([`status`], [énumération], [État global : accepté ou nécessitant relecture]),
      ([`fields_total`], [entier], [Nombre de champs prévus par le pack pays]),
      ([`fields_auto_accepted`], [entier], [Champs dont la confiance dépasse le seuil]),
      ([`localization`], [objet], [Pays détecté, gabarit employé, méthode de localisation, ancres trouvées]),
      ([`fields`], [dictionnaire], [Un objet par champ extrait, décrit ci-dessous]),
    ),
    largeurs: (auto, auto, 1fr),
  ),
  caption: [Structure du rapport produit pour chaque document],
  kind: table,
) <tab-report>

Chaque champ porte non seulement sa valeur, mais la trace de sa production : la
valeur lue par la passe page, celle lue par la passe recadrage, l'accord entre
les deux, la zone d'origine dans l'image, le score final et la bande de
confiance. Cette richesse répond au besoin BNF5 : une valeur doit pouvoir être
expliquée, non seulement affichée.

== Conclusion du chapitre

La conception traduit le principe d'honnêteté en décisions concrètes à chaque
étage, isole ce qui est propre à un pays dans de la configuration, et prévoit
deux voies d'intégration répondant à deux usages distincts. Le chapitre suivant
décrit la réalisation effective et les obstacles rencontrés.

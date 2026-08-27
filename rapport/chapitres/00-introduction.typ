#import "../template.typ": *

#heading(level: 1, numbering: none)[Introduction générale]

#heading(level: 2, numbering: none)[Le papier comme obstacle à l'identité légale]

Exister légalement suppose de pouvoir le prouver. L'acte de naissance est le
document qui ouvre l'accès à l'école, aux soins, à l'héritage, au vote et à
l'emploi formel : sans lui, une personne demeure administrativement invisible.
Les Nations unies en ont fait une cible explicite des Objectifs de Développement
Durable, la cible 16.9 visant à garantir à tous une identité juridique d'ici
2030, y compris l'enregistrement des naissances.

Or, dans de nombreux pays, une part considérable des actes existants n'est
disponible que sur papier : registres reliés conservés en mairie, copies
intégrales dactylographiées, extraits traduits, souches de volets. Ces documents
sont vulnérables — un incendie, une inondation ou simplement le temps suffisent
à les faire disparaître — et surtout inexploitables par les administrations
modernes, qui raisonnent sur des bases de données.

La numérisation de ces fonds est donc un enjeu de politique publique. Mais elle
se heurte à un obstacle très concret, rarement mis en avant : la ressaisie. Un
agent qui numérise un registre ne se contente pas de le photographier ; il doit
relire chaque acte et retaper chaque champ dans un formulaire. Cette opération
est lente, coûteuse, fastidieuse, et introduit ses propres erreurs.

#heading(level: 2, numbering: none)[Le sujet du stage]

Le présent stage part de ce constat. Il pose la question suivante : dans quelle
mesure les modèles vision-langage récents permettent-ils de transformer la
ressaisie en simple vérification ?

L'objectif n'est pas de supprimer l'humain de la boucle. Un acte d'état civil
est un document juridique : une erreur sur une date de naissance ou une
filiation a des conséquences durables sur la vie d'une personne. L'objectif est
de déplacer le travail humain, en le faisant passer de la saisie — mécanique,
répétitive, sans valeur ajoutée — à la vérification, qui mobilise le jugement.

Le travail réalisé comporte trois volets :

+ une chaîne de traitement qui lit un acte scanné et en extrait des champs
  structurés assortis d'un score de confiance, couvrant vingt-sept pays ;
+ une application web permettant le dépôt des documents, leur suivi et la
  correction humaine des valeurs extraites ;
+ une intégration au registre civil numérique #smallcaps[OpenCRVS], par laquelle
  les valeurs extraites pré-remplissent une déclaration de naissance.

#heading(level: 2, numbering: none)[Le fil conducteur : ne jamais affirmer faux]

Un principe unique gouverne les choix de conception de bout en bout, et il
mérite d'être énoncé dès l'introduction car il explique de nombreuses décisions
qui pourraient autrement paraître trop prudentes : #emph[le système préfère
avouer son incertitude plutôt qu'affirmer une valeur fausse avec assurance].

Un OCR qui se trompe en le signalant fait perdre quelques secondes à l'officier.
Un OCR qui se trompe en paraissant sûr de lui introduit une erreur dans un
registre d'état civil, où elle peut demeurer des décennies. Ces deux erreurs
n'ont pas le même coût, et le système est construit en conséquence : seuils de
confiance explicites, signalement des valeurs douteuses, refus de déduire ce que
le document ne dit pas.

Ce principe a une conséquence directe sur l'évaluation, présentée au
chapitre 5 : elle ne cherche pas à produire le chiffre le plus flatteur, mais le
chiffre le plus informatif, et elle expose ses échecs.

#heading(level: 2, numbering: none)[Organisation du rapport]

Le présent document suit la progression du travail.

Le #strong[chapitre 1] situe le projet : l'organisme d'accueil, le contexte de
l'état civil, la problématique, l'étude de l'existant et la méthodologie
adoptée.

Le #strong[chapitre 2] dresse l'état de l'art : reconnaissance optique
classique, modèles vision-langage, extraction d'informations clés, métriques
d'évaluation propres au domaine documentaire, et présentation d'#smallcaps[OpenCRVS].

Le #strong[chapitre 3] expose l'analyse et la conception : besoins, cas
d'utilisation, architecture générale, conception du pipeline, formalisation du
principe d'honnêteté et conception de l'intégration.

Le #strong[chapitre 4] détaille la réalisation, étape par étape, ainsi que les
difficultés techniques rencontrées et la manière dont elles ont été résolues.

Le #strong[chapitre 5] présente le protocole d'évaluation, les métriques
retenues et leur justification, les résultats obtenus, les erreurs relevées et
les limites de la démarche.

La #strong[conclusion] dresse le bilan et ouvre sur les perspectives.

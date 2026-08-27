#import "../template.typ": *

#heading(level: 1, numbering: none)[Conclusion générale]

#heading(level: 2, numbering: none)[Bilan du travail réalisé]

Ce stage est parti d'un constat simple : la numérisation des actes d'état civil
africains bute moins sur la photographie des registres que sur la ressaisie de
leur contenu. Le travail a consisté à transformer cette ressaisie en
vérification.

Le système réalisé lit un acte de naissance scanné, en extrait les champs à
l'aide d'un modèle vision-langage, les valide, leur associe un score de
confiance, puis pré-remplit une déclaration dans le registre civil numérique
#smallcaps[OpenCRVS]. Il couvre vingt-sept pays, traite un document en quarante
à quatre-vingt-dix secondes, et propose deux voies d'intégration répondant à
deux usages distincts : le traitement par lots d'un fonds d'archives, et le
traitement à l'unité au guichet, sans quitter le formulaire.

Les objectifs fixés en début de stage sont atteints. L'extensibilité à de
nouveaux pays se fait par configuration et non par code. Chaque valeur porte un
score exploitable. L'intégration ne modifie aucune ligne du cœur
d'#smallcaps[OpenCRVS], ce qui préserve la compatibilité avec ses mises à jour.
Une interface de vérification humaine existe, et les corrections y sont
capitalisées.

#heading(level: 2, numbering: none)[Ce que la démarche a apporté]

Au-delà du logiciel, trois enseignements se dégagent.

Le premier concerne le #strong[choix technologique]. Les modèles vision-langage
se sont montrés remarquablement robustes à l'hétérogénéité documentaire : ils
lisent un acte narratif malgache et un formulaire à cases malien sans
adaptation, là où une approche par gabarit aurait exigé un développement par
mise en page. Leur contrepartie, la capacité à produire une valeur plausible
mais fausse, s'est révélée maîtrisable à condition d'en faire une contrainte de
conception explicite plutôt qu'un risque résiduel.

Le deuxième concerne la #strong[nature réelle de la difficulté]. Le travail le
plus long n'a pas porté sur l'extraction elle-même, qui a fonctionné assez tôt,
mais sur les points de jonction entre systèmes : formats de réponse, mécanismes
de propagation des valeurs, contraintes non documentées de la plateforme cible.
Un symptôme unique, des champs restant vides, a recouvert successivement trois
causes distinctes, et seule l'inspection du code de la plateforme, plutôt que la
supposition de son fonctionnement, a permis d'aboutir.

Le troisième concerne l'#strong[évaluation]. Une première campagne, portant sur
des documents faciles et des champs simples, produisait des scores parfaits.
Élargir délibérément la mesure aux cas difficiles a fait apparaître des défauts
réels, dont un défaut systématique lié aux conventions d'écriture des noms. Une
évaluation incapable de constater un échec ne mesure rien : c'est probablement
l'enseignement méthodologique le plus durable de ce stage.

#heading(level: 2, numbering: none)[Limites]

Le système présente des limites qu'il convient de rappeler. Le découpage entre
prénom et nom de famille est erroné pour les conventions écrivant le patronyme
en premier et en majuscules. Les actes manuscrits, bien que traités, ne sont pas
couverts par les mesures de qualité. L'évaluation repose sur un échantillon
modeste dont les références n'ont pas été validées par un tiers indépendant.
Enfin, le recours à un modèle distant n'est pas acceptable en production pour
des données d'état civil, même si la bascule vers un modèle hébergé localement
est prévue par l'architecture.

#heading(level: 2, numbering: none)[Perspectives]

Plusieurs prolongements se dégagent naturellement.

À #strong[court terme], la correction du défaut d'ordre des noms, l'ajout des
champs de nationalité aux packs pays qui en sont dépourvus, et surtout
l'élargissement du jeu de référence avec une validation par un officier d'état
civil, qui lèverait la principale réserve méthodologique.

À #strong[moyen terme], la bascule vers un modèle hébergé localement, condition
de tout déploiement réel ; l'idempotence des envois, afin qu'un document
retransmis ne crée pas de doublon ; et la couverture de la reconnaissance
manuscrite, qui constitue à elle seule un sujet d'étude.

À #strong[long terme], le journal des corrections humaines accumulé par
l'application ouvre la voie à un affinage du modèle sur ce domaine documentaire
précis. Chaque correction effectuée par un officier constitue un exemple
d'entraînement : le système peut ainsi s'améliorer par son usage même, ce qui
est probablement la perspective la plus intéressante de ce travail.

#heading(level: 2, numbering: none)[Apport personnel]

Ce stage m'a permis de conduire un projet de bout en bout, depuis l'analyse d'un
besoin métier jusqu'à l'intégration dans une plateforme existante, en passant
par la conception, la réalisation et l'évaluation. Il m'a surtout appris qu'un
système destiné à un usage administratif sensible se juge autant à la manière
dont il gère son incertitude qu'à ses performances nominales, et qu'une mesure
honnête de ses limites vaut mieux qu'un chiffre flatteur.

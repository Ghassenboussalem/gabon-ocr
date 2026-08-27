#import "../template.typ": *

= Réalisation

Ce chapitre décrit la mise en œuvre effective : l'environnement technique, la
réalisation de chaque étape de la chaîne, les deux voies d'intégration, et les
difficultés rencontrées avec la manière dont elles ont été résolues.

== Environnement technique

#figure(
  tableau(
    3,
    ([Domaine], [Technologie], [Rôle dans le projet]),
    (
      ([Langage], [Python 3.12], [Pipeline d'extraction, application web, outillage]),
      ([Web], [FastAPI, Uvicorn], [Application de dépôt, de suivi et de correction]),
      ([Vision], [OpenCV, Pillow], [Prétraitement des images]),
      ([OCR], [Tesseract], [Repérage des étiquettes imprimées pour la localisation]),
      ([Modèle], [Modèle vision-langage via API], [Extraction des valeurs]),
      ([PDF], [pypdfium2], [Conversion des actes fournis en PDF]),
      ([Comparaison], [RapidFuzz], [Appariement approché des étiquettes et des lieux]),
      ([Registre], [OpenCRVS v1.9.14], [Plateforme cible de l'intégration]),
      ([Configuration], [TypeScript], [Panneau ajouté au formulaire de déclaration]),
      ([Infrastructure], [Docker, WSL], [Exécution locale de la plateforme OpenCRVS]),
      ([Tests], [pytest], [Tests hors-ligne du mapping et des règles]),
      ([Versionnement], [Git], [Suivi des évolutions et traçabilité des décisions]),
    ),
    largeurs: (auto, auto, 1fr),
  ),
  caption: [Environnement technique du projet],
  kind: table,
) <tab-techno>

== Réalisation du pipeline

=== Prétraitement

Le prétraitement corrige ce qui gêne la lecture sans altérer le contenu :
redressement de l'inclinaison, mise à l'échelle des documents de faible
résolution, amélioration du contraste et binarisation. Les documents fournis en
PDF sont convertis en image au préalable.

Une décision apparemment mineure s'est révélée importante par la suite : le
scan d'origine est conservé intact aux côtés des versions traitées. Elle a permis,
lorsque le besoin d'attacher la pièce justificative à la déclaration est apparu,
de disposer du document tel que l'officier l'a déposé, et non d'une version
retouchée pour la machine.

=== Localisation des champs

La localisation détermine où lire chaque information. Elle procède en deux temps.

D'abord, une #strong[localisation par gabarit] : les étiquettes imprimées du
formulaire sont repérées par #smallcaps[ocr] classique, puis appariées de
manière approchée aux étiquettes attendues du pack pays. Cet appariement
approché est nécessaire car l'#smallcaps[ocr] restitue rarement une étiquette
sans faute sur un document dégradé. Les positions trouvées définissent les zones
où lire les valeurs.

Ensuite, un #strong[contrôle de fiabilité] : si la proportion de champs
effectivement localisés tombe sous un seuil, le gabarit est considéré comme
inadapté — mise en page inconnue, page multiple, scan de mauvaise qualité — et
la chaîne bascule vers une localisation confiée au modèle vision-langage.

C'est la première application concrète du principe d'honnêteté : plutôt que de
produire des zones fausses mais d'apparence normale, le système reconnaît que le
gabarit ne convient pas.

La @fig-boxes montre la visualisation produite pour contrôle.

#figure(
  image("../figures/capture_field_boxes.png", width: 68%),
  caption: [Visualisation des zones détectées, produite pour chaque document et
    servant au contrôle qualité de la localisation],
) <fig-boxes>

=== Extraction en deux passes

L'extraction interroge le modèle deux fois, comme prévu à la conception.

La mise en œuvre initiale traitait chaque zone recadrée par un appel distinct,
ce qui portait le temps de traitement à environ dix minutes par document —
incompatible avec le besoin BNF1. Trois optimisations ont ramené ce temps à une
fourchette de quarante à quatre-vingt-dix secondes :

+ #strong[Le regroupement] : les zones sont envoyées par lots de cinq images par
  appel plutôt qu'une par une.
+ #strong[La parallélisation] : quatre lots sont traités simultanément.
+ #strong[La limitation du raisonnement] : le budget de réflexion interne du
  modèle est plafonné, la tâche relevant de la lecture et non du raisonnement.

Une gestion des quotas complète le dispositif : plusieurs clés d'accès sont
configurées et la chaîne bascule automatiquement de l'une à l'autre lorsqu'une
limite est atteinte.

=== Validation et score de confiance

La validation convertit et contrôle. Elle transforme les dates écrites en toutes
lettres — fréquentes dans les actes narratifs — en dates normalisées, vérifie la
cohérence chronologique, et rapproche les lieux du lexique du pays.

Le score de confiance de chaque champ agrège trois signaux : la confiance
déclarée par le modèle, l'accord entre les deux passes d'extraction, et le
résultat des règles de validation. Les champs sont ensuite répartis en trois
bandes, et le seuil retenu détermine ce que l'officier devra relire.

== Les packs pays

Vingt-sept pays sont couverts, chacun décrit par un répertoire de configuration.
Le @tab-pays présente la répartition par type de document, révélatrice de
l'hétérogénéité du corpus.

#figure(
  tableau(
    3,
    ([Type de document], [Caractéristiques], [Exemples de pays]),
    (
      ([Copie intégrale narrative], [Acte rédigé en prose continue, information dispersée dans le texte],
       [Côte d'Ivoire, Madagascar, Algérie]),
      ([Formulaire à champs étiquetés], [Étiquettes imprimées, valeurs dactylographiées ou manuscrites],
       [Mali, Tunisie, Mauritanie]),
      ([Volet à souche], [Feuillet détachable, information condensée],
       [Bénin, Togo]),
      ([Extrait traduit], [Traduction certifiée d'un acte en langue étrangère],
       [Nigéria, Sierra Leone, Afrique du Sud]),
      ([Registre manuscrit], [Acte rempli à la main dans un registre imprimé],
       [Cameroun, Gabon, Sénégal, Rwanda]),
    ),
    largeurs: (auto, 1fr, auto),
  ),
  caption: [Typologie des documents du corpus par famille de mise en page],
  kind: table,
) <tab-pays>

Cette diversité justifie a posteriori le choix d'un modèle vision-langage : une
approche par gabarit seule n'aurait pas absorbé l'écart entre un acte narratif
malgache et un formulaire à cases malien.

== L'application web

L'application web constitue le point d'entrée humain du système. Elle offre
trois fonctions.

Le #strong[dépôt] accepte les images et les PDF par glisser-déposer. Il propose
également un code #smallcaps[qr] : l'officier le scanne avec un téléphone, ce
qui ouvre une page de capture permettant de photographier l'acte directement.
Cette voie répond au cas d'usage réel du terrain, où le poste de travail n'est
pas toujours équipé d'un scanner.

Le #strong[suivi] affiche l'avancement de chaque document. Le traitement
s'exécutant en processus séparé, une défaillance sur un document n'interrompt ni
le serveur ni les autres traitements.

La #strong[correction] présente chaque valeur extraite en regard du recadrage
dont elle provient, les champs les moins sûrs en premier. Chaque correction est
journalisée. Ce journal constitue un actif pour la suite : il rassemble des
couples associant ce que le modèle a lu et ce qu'un humain a corrigé, matière
première d'un affinage ultérieur du modèle.

== Intégration à OpenCRVS

=== Le mapping vers la déclaration

Le passage des champs extraits à une déclaration #smallcaps[OpenCRVS] mobilise
plusieurs conversions non triviales :

/ La table d'alias: elle ramène les vocabulaires des vingt-sept packs vers les
  identifiants du formulaire cible.

/ La séparation des noms: le formulaire attend un prénom et un nom de famille
  distincts, là où l'acte fournit souvent une chaîne unique. La règle exploite
  la convention des actes francophones, qui écrivent le nom de famille en
  majuscules. Cette règle a ses limites, mesurées au chapitre 5.

/ La normalisation des énumérations: le sexe, écrit « Masculin », « M » ou
  « MASCULIN » selon les actes, est converti vers la valeur attendue.

/ La conversion des nationalités: les adjectifs de nationalité sont convertis en
  codes pays normalisés. Les cas ambigus ne sont jamais tranchés.

/ La résolution des lieux: lorsque l'acte ne mentionne qu'une ville, le modèle
  est interrogé pour obtenir la hiérarchie administrative correspondante. Cette
  résolution n'est retenue qu'au-dessus d'un seuil de confiance, et le résultat
  est toujours signalé comme « à confirmer ».

Tout ce qui ne peut pas être placé dans un champ structuré — heure de naissance,
nom de l'officier, mentions marginales — n'est pas perdu pour autant : ces
valeurs sont reportées dans le commentaire de revue, avec leur score. L'officier
voit ainsi l'intégralité de ce que le système a lu.

=== Voie par notification

Cette voie enchaîne quatre appels : obtention d'un jeton, création de
l'événement, téléversement du scan, puis envoi de la déclaration accompagnée de
sa pièce jointe. La déclaration pré-remplie apparaît dans la file de travail de
l'officier.

=== Voie intégrée au formulaire

Cette voie ajoute au formulaire de déclaration un panneau permettant de déposer
un scan sans quitter #smallcaps[OpenCRVS]. Elle a été réalisée en s'inspirant
d'un mécanisme déjà présent dans la plateforme : le lecteur d'identité, qui
interroge un service externe et injecte les valeurs obtenues dans le formulaire.

L'ensemble tient dans un fichier de configuration ajouté au dépôt de
configuration pays. Aucune ligne du cœur d'#smallcaps[OpenCRVS] n'a été
modifiée, ce qui satisfait le besoin BNF3 et garantit la compatibilité avec les
mises à jour de la plateforme.

== Difficultés rencontrées

Cette section rend compte des obstacles réels du projet. Elle figure ici parce
que leur résolution constitue une part substantielle du travail d'ingénierie, et
parce que les mentionner permet à un lecteur reprenant le sujet d'éviter les
mêmes impasses.

#figure(
  tableau(
    3,
    ([Difficulté], [Diagnostic], [Résolution]),
    (
      ([Temps de traitement d'environ dix minutes par acte],
       [Un appel au modèle par zone recadrée],
       [Regroupement par lots, parallélisation, limitation du raisonnement interne : environ une minute]),
      ([Épuisement des quotas d'appel au modèle],
       [Limite journalière de l'offre gratuite],
       [Rotation automatique entre plusieurs clés ; échec explicite plutôt que silencieux]),
      ([Champs vides malgré une extraction correcte],
       [Le vocabulaire du pack ne correspondait pas aux identifiants attendus],
       [Table d'alias couvrant les vingt-sept packs]),
      ([Déclaration invisible dans la file de travail],
       [Identifiant de bureau devenu obsolète après réinitialisation de la base],
       [Synchronisation automatique de l'identifiant au démarrage]),
      ([Impossibilité d'envoyer le fichier au service depuis le formulaire],
       [Le type de champ concerné ne transmet que du texte structuré],
       [Téléversement vers le stockage d'OpenCRVS, puis transmission du seul chemin]),
      ([Valeurs produites mais champs restant vides],
       [Un champ ne se synchronise que si sa configuration déclare la source comme parente],
       [Déclaration conjointe de la source et de la valeur sur chaque champ concerné]),
      ([Champs encore vides après cette correction],
       [La réponse exposait des clés contenant des points, illisibles pour le mécanisme de résolution],
       [Ajout d'une représentation réellement imbriquée dans la réponse]),
      ([Rendu du panneau dégradé et erreurs affichées],
       [Les balises HTML des libellés sont interprétées comme une syntaxe de formatage],
       [Suppression des balises ; remplacement de l'image intégrée par un bouton]),
      ([Une vingtaine de terminaux ouverts à chaque démarrage],
       [Chaque tâche planifiée ouvrait sa console ; en fermer une arrêtait le service],
       [Lancement par un script masquant la fenêtre, sans élévation de privilèges]),
    ),
    largeurs: (1fr, 1.1fr, 1.2fr),
  ),
  caption: [Principales difficultés techniques rencontrées et leur résolution],
  kind: table,
) <tab-difficultes>

Trois de ces difficultés méritent un commentaire, car elles illustrent une même
leçon : une chaîne d'intégration peut échouer silencieusement à chacun de ses
maillons, et seul un diagnostic mené maillon par maillon permet de trouver le
bon.

Le cas des champs restant vides malgré un pré-remplissage correct en est
l'illustration la plus nette. Trois causes différentes ont produit exactement le
même symptôme : d'abord un vocabulaire de champs non concordant, puis une
propriété de configuration manquante, enfin un format de réponse incompatible
avec le mécanisme de résolution des valeurs. Chaque correction paraissait avoir
résolu le problème jusqu'à ce que le symptôme réapparaisse. Ce n'est qu'en
examinant le code de la plateforme, plutôt qu'en supposant son fonctionnement,
que la cause finale a été identifiée.

== Industrialisation de l'environnement

Une part non négligeable du travail a porté sur la fiabilité de l'environnement
de développement. Faire fonctionner simultanément quatorze microservices, six
composants d'infrastructure et l'application développée exige un outillage
propre.

Un script unique démarre l'ensemble, affiche l'état de chaque service, relance
automatiquement ceux qui ne répondent pas, puis vérifie la cohérence de la
configuration d'intégration. Les pièges découverts en cours de stage — perte de
configuration après un arrêt brutal, identifiants régénérés, processus résiduels
après redémarrage — sont détectés et corrigés automatiquement lorsque c'est
possible, signalés explicitement sinon.

== Conclusion du chapitre

La réalisation a confirmé la validité de la conception, tout en révélant que la
difficulté principale ne résidait pas dans l'extraction elle-même — le modèle
lit correctement des documents difficiles — mais dans les points de jonction
entre systèmes. Le chapitre suivant mesure la qualité effectivement obtenue.

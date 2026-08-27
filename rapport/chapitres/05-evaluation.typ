#import "../template.typ": *

= Évaluation et résultats

Ce chapitre présente la démarche d'évaluation, les résultats obtenus, les
erreurs relevées et les limites de la mesure. Il occupe une place importante
dans ce rapport pour une raison de fond : un système d'extraction dont on ne
sait pas mesurer la qualité ne peut pas être déployé sur un registre juridique.

== Deux questions distinctes

L'évaluation répond à deux questions qu'il serait trompeur de confondre.

/ La justesse: quand le système lit un champ, lit-il la bonne valeur ? Cette
  question exige des valeurs de référence auxquelles comparer les sorties.

/ Le rendement: sur un lot représentatif, quelle proportion du travail de saisie
  est effectivement épargnée à l'officier ? Cette question se mesure sans
  référence, sur l'ensemble des documents traités.

Un système peut être très juste sur les rares champs qu'il ose remplir, tout en
n'épargnant presque aucun travail ; il peut inversement remplir beaucoup de
champs de façon peu fiable. Seule la lecture conjointe des deux mesures a du
sens.

== Protocole d'évaluation de la justesse

=== Constitution du jeu de référence

Un jeu de référence a été constitué en transcrivant les valeurs attendues
directement depuis les actes. Il couvre neuf documents et soixante-neuf champs.

Le choix des documents obéit à un critère explicite : #emph[couvrir le difficile
autant que le facile]. Une première version de l'évaluation, portant sur six
documents bien lisibles et cinq champs simples, produisait des scores parfaits
sur toute la ligne. Ce résultat était une propriété de l'évaluation, non du
système : une mesure incapable de constater un échec ne mesure rien. Le jeu a
donc été élargi pour inclure une copie dactylographiée à l'encre pâlie, un acte
mentionnant l'âge des parents au lieu de leur date de naissance, et un acte
narratif dense.

Les champs évalués ont été étendus de la même manière : au-delà de l'identité de
l'enfant et du nom des parents, l'évaluation porte désormais sur les dates de
naissance des parents, leurs professions et leurs nationalités — champs
nettement plus difficiles. Plusieurs de ces champs sont délibérément vides dans
la référence, lorsque l'acte ne les mentionne pas : produire une valeur pour
ceux-là compte alors comme une hallucination.

=== Traitement particulier des noms

Les noms font l'objet d'une double mesure, pour une raison méthodologique.

Les actes n'écrivent pas les noms dans le même ordre selon les pays : le nom de
famille précède le prénom au Nigéria, au Bénin et au Mali, alors qu'il le suit
en Côte d'Ivoire ou en Tunisie. Comparer l'ordre imprimé reviendrait à évaluer
une convention typographique plutôt que la qualité de lecture. Le nom est donc
comparé indépendamment de l'ordre des mots.

Mais la répartition entre prénom et nom de famille compte réellement, puisque le
formulaire cible comporte deux champs distincts. Elle fait donc l'objet d'une
mesure séparée.

Cette distinction n'est pas cosmétique : elle a permis de mettre en évidence un
défaut systématique qui serait autrement resté confondu avec du bruit.

=== Métriques retenues

Les métriques sont celles justifiées au chapitre 2 : #smallcaps[anls] comme
indicateur principal, taux d'erreur au caractère et au mot, précision, rappel et
#smallcaps[f1] en correspondance exacte et approchée, taux d'hallucination et
conformité au schéma.

== Résultats de justesse

Le @tab-resultats présente les résultats mesurés sur les neuf documents.

#figure(
  tableau(
    3,
    ([Métrique], [Valeur], [Lecture]),
    (
      ([ANLS], [0,967],
       [Les valeurs lues sont très proches des références attendues]),
      ([F1 correspondance exacte], [0,926],
       [Neuf champs sur dix sont strictement identiques à la référence]),
      ([F1 correspondance approchée], [0,985],
       [Les écarts restants sont, pour l'essentiel, mineurs]),
      ([Précision (exacte)], [0,940],
       [Parmi les valeurs affirmées, la grande majorité est exacte]),
      ([Rappel (exact)], [0,913],
       [La plupart des champs présents dans l'acte sont produits]),
      ([Taux d'erreur caractère], [0,005],
       [Un demi-caractère erroné pour cent caractères lus]),
      ([Taux d'erreur mot], [0,034],
       [Environ trois mots sur cent diffèrent de la référence]),
      ([Couverture], [97,1 %],
       [Presque tous les champs présents dans l'acte reçoivent une valeur]),
      ([Taux d'hallucination], [0 %],
       [Aucune valeur produite pour un champ absent du document]),
      ([Conformité au schéma], [100 %],
       [Toutes les valeurs sont directement exploitables par OpenCRVS]),
      ([Découpage prénom / nom], [81,5 %],
       [Un nom sur cinq est mal réparti entre les deux champs]),
    ),
    largeurs: (auto, auto, 1fr),
  ),
  caption: [Résultats de justesse sur neuf actes et soixante-neuf champs],
  kind: table,
) <tab-resultats>

Trois observations méritent d'être soulignées.

Le #strong[taux d'hallucination nul] est le résultat le plus significatif au
regard de l'objectif du projet. Plusieurs champs de la référence sont
volontairement vides — un acte algérien indique l'âge des parents et non leur
date de naissance — et le système n'a produit aucune valeur pour ceux-là. Le
principe d'honnêteté produit ici un effet mesurable.

La #strong[conformité au schéma de 100 %] signifie qu'aucune valeur produite ne
nécessite de retraitement avant injection dans le registre.

Le #strong[découpage prénom / nom à 81,5 %] est le point faible identifié, et
il est analysé plus loin.

La @fig-anls détaille la justesse champ par champ.

#figure(
  image("../figures/chart_anls_par_champ.png", width: 92%),
  caption: [Similarité ANLS par champ évalué],
) <fig-anls>

#figure(
  image("../figures/chart_exact_par_document.png", width: 92%),
  caption: [Proportion de champs strictement exacts par document],
) <fig-doc>

== Erreurs relevées

L'évaluation relève six champs erronés ou manquants sur soixante-neuf, et cinq
inversions entre prénom et nom. Ils sont énumérés au @tab-erreurs plutôt que
résumés : un rapport d'évaluation qui n'expose pas ses échecs ne permet pas
d'apprécier la portée de ses réussites.

#figure(
  tableau(
    4,
    ([Document], [Champ], [Attendu], [Obtenu]),
    (
      ([Madagascar], [Date de naissance], [1999-07-08], [1989-07-08]),
      ([Madagascar], [Nom du père], [Zafindratovo], [Zafindrat]),
      ([Mali], [Nom de la mère], [FATOUMATA], [FATOUKATA]),
      ([Sierra Leone], [Nationalité du père], [SLE], [non extrait]),
      ([Sierra Leone], [Nationalité de la mère], [SLE], [non extrait]),
      ([Côte d'Ivoire], [Profession du père], [Directeur de la Radiodiffusion de la Côte d'Ivoire], [variante de ponctuation]),
    ),
    largeurs: (auto, auto, 1fr, 1fr),
  ),
  caption: [Champs erronés ou manquants relevés par l'évaluation],
  kind: table,
) <tab-erreurs>

Ces erreurs se répartissent en trois natures, dont la gravité diffère
considérablement.

/ L'erreur de lecture de chiffre: sur l'acte malgache, l'année 1999, écrite en
  toutes lettres au sein d'une phrase continue, a été lue 1989. C'est de loin
  l'erreur la plus préoccupante : une date reste plausible même lorsqu'elle est
  fausse, et rien dans sa forme ne signale le problème. Un officier qui ne
  relirait pas ce champ l'inscrirait tel quel dans le registre. Cette erreur
  unique justifie à elle seule le maintien d'une vérification humaine.

/ Les erreurs de caractère: sur la copie malienne dactylographiée à l'encre
  pâlie, un prénom a été lu FATOUKATA au lieu de FATOUMATA, et un prénom
  malgache a été tronqué. Ces erreurs sont visibles : un officier les repère
  immédiatement en regardant le document. Leur coût est faible.

/ Les valeurs non extraites: les nationalités sierra-léonaises n'ont pas été
  produites, non par échec de lecture, mais parce que le pack pays correspondant
  ne comportait pas de champ pour les recevoir. Ce n'est pas une limite du
  modèle mais une lacune de configuration, corrigée pour un pays et à étendre
  aux autres.

=== Le défaut systématique : l'ordre des noms

Les cinq inversions relevées ne sont pas dispersées au hasard : elles se
concentrent sur les actes béninois et maliens, c'est-à-dire ceux qui écrivent le
nom de famille avant le prénom et intégralement en majuscules.

La cause est identifiée. La règle de séparation s'appuie sur la casse : dans les
actes francophones, le nom de famille est habituellement en majuscules et le
prénom en minuscules. Lorsque l'ensemble du nom est en majuscules, ce signal
disparaît, et la règle retombe sur une convention par défaut — le dernier mot
est le nom de famille — qui se trouve être fausse pour ces pays.

Deux correctifs sont envisageables. Le premier consiste à exploiter le nom de
famille de l'enfant, souvent connu par un champ explicitement étiqueté, lorsque
ce même mot apparaît dans le nom d'un parent : les familles partagent leur
patronyme. Le second consiste à déclarer l'ordre des noms dans la configuration
du pays, cette convention étant nationale et stable.

Ce défaut est signalé plutôt que corrigé dans l'urgence. Le corriger sans
disposer d'un jeu de validation plus large ferait courir un risque de régression
sur les autres pays, dont le comportement actuel est correct. La démarche
d'évaluation aurait perdu son sens si elle avait servi à justifier une
correction non validée.

== Rendement sur le lot d'échantillons

La seconde question — combien de saisie est effectivement épargnée — se mesure
sans référence, sur un lot plus large.

#figure(
  tableau(
    2,
    ([Indicateur], [Valeur]),
    (
      ([Documents évalués (actes tapés)], [21]),
      ([Champs détectés par document, en moyenne], [environ 23]),
      ([Champs auto-acceptés, en moyenne], [environ 57 %]),
      ([Champs OpenCRVS pré-remplis par document, en moyenne], [environ 7]),
      ([Temps de traitement par document], [40 à 90 secondes]),
    ),
    largeurs: (1fr, auto),
  ),
  caption: [Rendement mesuré sur le lot d'échantillons],
  kind: table,
) <tab-rendement>

La @fig-confiance présente la répartition des scores de confiance sur ce lot.

#figure(
  image("../figures/chart_confiance.png", width: 58%),
  caption: [Répartition des champs par bande de confiance],
) <fig-confiance>

Un champ « auto-accepté » est un champ dont la confiance dépasse le seuil et qui
ne fait donc l'objet d'aucun signalement. Les champs situés sous le seuil sont
néanmoins pré-remplis, mais explicitement marqués « à vérifier ». Cette
distinction est au cœur du dispositif : elle indique à l'officier où porter son
attention, au lieu de le contraindre à tout relire.

== Limites de la démarche

Trois réserves doivent accompagner ces chiffres. Les taire donnerait une
apparence de solidité que la mesure ne possède pas encore.

/ La taille de l'échantillon: neuf documents et soixante-neuf champs constituent
  un jeu modeste. Les intervalles de confiance associés à des proportions
  calculées sur un tel effectif sont larges, et un document supplémentaire
  particulièrement difficile déplacerait sensiblement les résultats.

/ L'origine des références: les valeurs de référence ont été transcrites dans le
  cadre de ce projet, et non produites par un annotateur indépendant. Une erreur
  de lecture commise à la fois par le système et par la transcription resterait
  invisible. C'est la limite méthodologique la plus sérieuse.

/ Le périmètre: les actes manuscrits sont exclus de ces mesures. La
  reconnaissance d'écriture manuscrite constitue un problème distinct et
  nettement plus difficile ; les inclure aurait masqué la performance réelle sur
  la cible du projet, mais leur exclusion signifie que les chiffres ne
  s'appliquent pas à eux.

#reserve("Ce que ces résultats établissent, et ce qu'ils n'établissent pas")[
  Ils établissent que le système traite correctement les documents évalués, que
  ses sorties sont directement exploitables par le registre cible, et qu'il
  n'invente pas de valeurs. Ils n'établissent pas une absence d'erreurs en
  général. La levée de la principale réserve passe par la vérification d'une
  partie des références par un officier d'état civil, ce qui romprait la
  dépendance entre le système mesuré et la mesure.
]

== Reproductibilité

L'ensemble des chiffres présentés est recalculable. Les valeurs de référence
sont versionnées avec leur provenance, les métriques sont produites par deux
programmes exécutables en une commande, et le rapport d'évaluation détaillé est
généré à partir de leurs sorties, sans aucune valeur saisie manuellement. Une
modification du système suivie d'une nouvelle exécution suffit à obtenir des
chiffres à jour.

== Conclusion du chapitre

Le système atteint une justesse élevée sur les documents évalués, ne produit
aucune valeur inventée, et fournit des sorties directement exploitables. Il
présente un défaut systématique identifié et documenté sur l'ordre des noms dans
certaines conventions nationales, et une erreur de lecture de date qui rappelle
pourquoi la vérification humaine demeure nécessaire. La mesure elle-même
comporte des limites qui sont énoncées plutôt que masquées.

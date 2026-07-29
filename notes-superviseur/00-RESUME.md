# Résumé du projet — OCR d'actes d'état civil → OpenCRVS

> Objectif : numériser des actes de naissance africains (scans papier) et
> pré-remplir automatiquement des déclarations de naissance dans OpenCRVS,
> pour que l'officier d'état civil n'ait plus qu'à **vérifier** au lieu de
> **ressaisir**.

## Ce qui fonctionne aujourd'hui (démontrable en direct)

1. **Pipeline OCR multi-pays** : un scan (photo, image ou PDF) → JSON structuré
   avec un score de confiance par champ. **27 pays couverts** + un mode
   générique. Détection automatique du pays. ~35–50 s par document.
2. **Application web** : dépôt par glisser-déposer ou **par téléphone via QR
   code**, suivi du traitement en direct, écran de relecture/correction,
   bouton « → OpenCRVS » par document.
3. **Intégration OpenCRVS** (API officielle *Event Notification*, V2 events) :
   la déclaration arrive **pré-remplie** dans la file *Notifications* du
   bureau d'état civil, **avec le scan original en pièce jointe** (« Proof of
   birth »). Flux complet mesuré : **46 secondes** de l'upload au registre.

## Ce qui est pré-rempli automatiquement (exemple réel : extrait tunisien)

| Champ OpenCRVS | Valeur extraite |
|---|---|
| Nom de l'enfant | ALI YAHIA |
| Sexe / Date de naissance | Masculin / 10-03-1981 |
| Lieu de naissance | Other → Tunisie → Médenine → Ben Guerdane → CP 4160 (**résolu automatiquement** à partir de la seule mention « BEN GUERDANE ») |
| Nom du père / de la mère | complets, prénom/nom séparés |
| Nationalité des parents | Tunisia (code ISO déduit de « TUNISIENNE ») |
| Pièce jointe | le scan original, visible dans le panneau de revue |

Tout ce qui n'est pas structurable de façon **sûre** (heure de naissance,
officier, mentions marginales…) est reporté dans le **commentaire de revue**
avec son score de confiance — l'officier voit tout, rien n'est perdu, rien
n'est inventé.

## Principe directeur : le « gate d'honnêteté »

À chaque étage, le système préfère **ne rien remplir** plutôt que remplir
faux avec assurance :
- localisation des champs : si le gabarit ne colle pas (couverture < 0.6),
  bascule sur un grounding VLM ; jamais de cadres « confiants mais faux » ;
- valeurs sous le seuil de confiance 0.6 : pré-remplies mais **signalées
  « à vérifier »** dans le commentaire ;
- résolution de lieux : appliquée uniquement si confiance ≥ 0.7, sinon
  commentaire seulement ; catégorie (hôpital/domicile) jamais devinée ;
- nationalité ambiguë (ex. « CONGOLAISE » : deux Congo) : jamais choisie à
  la place de l'humain.

## Chiffres clés

- 27 packs pays, 28 schémas de champs, ~200 noms de champs recensés et mappés
- ~35–50 s de traitement par document (10 min au début du projet → ×12)
- 46 s upload → dossier pré-rempli dans OpenCRVS
- **Évaluation sur 18 documents typés/imprimés (1 par pays, hors manuscrits)** :
  **Précision 100 % · Rappel 85.0 % · F1 91.9 %** sur les champs pré-remplis
  automatiquement, 58.7 % des champs auto-acceptés en moyenne, 7.1 champs
  OpenCRVS pré-remplis par document en moyenne → détail complet dans
  `06-metriques-evaluation.md`
- 0 modification du code OpenCRVS : tout passe par l'API standard
  *Event notification* → **migration vers une vraie instance = changer 4
  lignes de configuration** (URLs + identifiants du client d'intégration)

## Fichiers de ce dossier

- `01-pipeline-ocr.md` — le pipeline d'extraction en détail
- `02-application-web.md` — l'application de dépôt/relecture
- `03-integration-opencrvs.md` — le mapping et l'API OpenCRVS
- `04-infrastructure-locale.md` — le banc d'essai OpenCRVS complet sur ce PC
- `06-metriques-evaluation.md` — **métriques d'évaluation sur le lot d'échantillons** (généré par `tools/evaluate_batch.py`, à relancer après chaque nouveau lot traité)
- `metriques_par_document.csv` — détail brut par document
- `05-limites-et-roadmap.md` — limites connues, prochaines étapes

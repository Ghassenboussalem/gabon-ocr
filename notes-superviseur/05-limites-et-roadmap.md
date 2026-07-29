# 5. Limites connues et prochaines étapes

## Limites assumées (et pourquoi)

- **Gemini (API Google) pour le POC** : rapide et gratuit pour prototyper,
  mais des données d'état civil ne doivent pas transiter par une API tierce
  en production → le pipeline supporte déjà `--backend ollama/openai` pour
  basculer sur un VLM hébergé localement, sans changement de code.
- **Quotas free tier** : ~250 requêtes/jour/clé (rotation automatique de
  clés) — suffisant pour la démo, pas pour la production.
- **Noms arabes en majuscules** (« HEDI BEN AMMAR BEN DHAOU ») : le découpage
  prénom/nom est imparfait ; la valeur brute reste visible dans le
  commentaire pour correction en un clic.
- **Catégorie du lieu d'accouchement** (hôpital/domicile) : jamais devinée —
  l'acte ne la précise généralement pas.
- **Champs absents des actes** (email de l'informant, type de pièce
  d'identité…) : resteront toujours à la charge de l'officier.
- **Les envois ne sont pas idempotents** : renvoyer un document crée un
  doublon dans la file (correction prévue : transactionId = hash du fichier).
- **Instance de démo Farajaland** : les lieux du pays réel ne peuvent pas
  être mappés vers des zones administratives internes tant qu'on n'est pas
  sur l'instance cible ; en attendant, adresse « internationale » complète.

## Prochaines étapes proposées

1. ✅ **Batch d'évaluation** — fait, voir `06-metriques-evaluation.md`
   (21/27 échantillons traités ; 6 restants bloqués par le quota Gemini
   gratuit du jour, à relancer). Reste à élargir la relecture humaine
   (`data/corrections.jsonl`) pour fiabiliser le taux d'erreur réel, et à
   comprendre pourquoi 2 documents sont tombés sur le pack générique au lieu
   d'un pack pays dédié.
2. **Idempotence** des envois (hash du fichier comme transactionId) + case
   « envoi automatique après traitement ».
3. **Afficher le tracking ID** OpenCRVS (ex. JGQ7O3) dans l'app web avec lien
   direct vers le dossier.
4. **Migration** sur l'instance de référence : création d'un client
   d'intégration par son administrateur, changement de 4 variables de
   configuration — démonstration possible le jour même.
5. (Après accord) page « téléverser un scan » **dans** le formulaire OpenCRVS
   lui-même (FieldTypes FILE+HTTP du toolkit V2, sur le modèle du lecteur
   d'identité MOSIP déjà présent dans le countryconfig).
6. **Fine-tuning** : `corrections.jsonl` (corrections humaines accumulées)
   comme jeu d'entraînement pour améliorer l'extraction.

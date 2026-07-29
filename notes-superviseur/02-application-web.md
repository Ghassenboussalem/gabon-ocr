# 2. Application web de dépôt et relecture

FastAPI (`review/app.py`), port 8000 en local ; déployée aussi sur Render
(https://gabon-ocr.onrender.com, protégée par mot de passe, plan gratuit).

## Parcours utilisateur

1. **Dépôt** (`/`) : glisser-déposer d'images ou PDF, ou **QR code** à
   scanner avec un téléphone → page mobile pour photographier l'acte
   directement. Liste des documents avec statut de traitement en direct.
2. **Relecture** (`/review`) : les champs extraits côte à côte avec le scan ;
   les corrections manuelles sont journalisées dans `data/corrections.jsonl`
   (→ futur jeu de données de fine-tuning).
3. **Envoi** : bouton **« → OpenCRVS »** par document → la déclaration
   pré-remplie part vers l'instance OpenCRVS ; un badge « CRVS ✓ » confirme
   (event id en infobulle).

## Points techniques

- Le traitement est asynchrone : chaque upload lance le pipeline en
  sous-processus, l'interface interroge le statut.
- Sessions téléphone éphémères (QR par session), sans authentification à
  ressaisir sur le mobile.
- En local, l'application tourne comme tâche planifiée Windows
  (`gabonocr-webapp`) et écoute sur le réseau local pour que le QR
  fonctionne depuis un téléphone sur le même Wi-Fi.

# 4. Banc d'essai : OpenCRVS complet sur un PC portable

Pour développer et démontrer sans toucher à aucune instance de production,
**la totalité d'OpenCRVS v1.9.14** (même version que l'instance de
référence) tourne sur ce PC Windows (14 Go de RAM) :

- distro WSL dédiée (`ubuntu-opencrvs`) + Docker Desktop : MongoDB,
  Elasticsearch, PostgreSQL, MinIO, Redis, InfluxDB ;
- les ~14 microservices OpenCRVS (auth, gateway, workflow, events, client,
  login, countryconfig…) chacun dans sa **tâche planifiée Windows** avec
  scripts de lancement **idempotents** (un redémarrage ne crée jamais de
  processus en double) ;
- le countryconfig utilisé est un fork du dépôt de référence (branche
  `main-poc`), le dépôt d'origine n'est jamais modifié.

## Exploitation en une commande

```powershell
powershell -ExecutionPolicy Bypass -File start-opencrvs.ps1
```

Le script démarre tout, affiche un tableau de bord live, **auto-répare** les
services en panne, puis vérifie de bout en bout l'intégration OCR (token du
client d'intégration + cohérence de l'UUID du bureau) et affiche la marche à
suivre si quelque chose manque. Fin attendue : « TOUT EST VERT ».

## Leçons d'exploitation (documentées dans HANDOFF.md)

- un arrêt brutal du PC peut faire « rollbacker » MongoDB → le client
  d'intégration disparaît ; le script de démarrage le détecte désormais
  automatiquement ; parade : `wsl --shutdown` avant d'éteindre ;
- les identifiants (UUID) de lieux changent à chaque re-seed → le script
  resynchronise la configuration automatiquement ;
- tous les pièges rencontrés (et leurs remèdes) sont consignés pour la
  reprise du projet par un tiers.

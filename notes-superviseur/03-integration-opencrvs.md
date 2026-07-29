# 3. Intégration OpenCRVS

**Zéro modification du code OpenCRVS.** Tout passe par l'API officielle
*Event Notification* (v1.9, V2 events), conçue précisément pour les
notifications de naissance envoyées par des systèmes tiers de confiance
(hôpitaux…) — notre OCR joue ce rôle.

## Flux (3 appels HTTP)

```
POST {auth}/token                        client_credentials (client d'intégration)
POST {gateway}/events/events             création de l'événement « birth »
POST {gateway}/upload                    scan original → MinIO (multipart)
POST {gateway}/events/events/notifications   déclaration pré-remplie + pièce jointe
```

Code : `pipeline/opencrvs_export.py` (mapping) + `tools/send_to_opencrvs.py`
(CLI, avec `--dry-run` pour inspecter le payload sans envoyer).
Tests : `tests/test_opencrvs_export.py` (hors-ligne, 6 tests).

## Le mapping `report.json` → déclaration V2

- **Table d'alias multi-pays** : les 28 schémas nomment différemment la même
  chose (`enfant_nom` vs `nom`+`prenoms` vs `pere_nom_complet`…) ; tous les
  vocabulaires convergent vers les identifiants du formulaire V2.
- **Noms** : composition directe prénom/nom quand l'acte les sépare ; sinon
  heuristique « MAJUSCULES = nom de famille » des actes francophones.
- **Nationalités** : adjectifs français (« TUNISIENNE ») → codes ISO3 du champ
  COUNTRY (36 nationalités couvertes). Cas ambigus (« CONGOLAISE ») → jamais
  devinés, reportés en commentaire.
- **Lieu de naissance** : quand l'acte ne donne qu'une ville, le VLM résout
  la hiérarchie administrative (gouvernorat/état, district, code postal) et
  remplit une adresse internationale (catégorie « Other » — hôpital/domicile
  jamais deviné). Gate de confiance ≥ 0.7, cache par document.
- **Pièce jointe** : le scan original est téléversé dans MinIO et attaché en
  « Proof of birth » — l'officier a l'acte sous les yeux dans le panneau de
  revue.
- **Commentaire de revue** : tout ce qui n'est pas structurable (heure,
  officier, mentions, références de registre…) y figure avec son score de
  confiance ; les valeurs pré-remplies sous 0.6 y sont marquées « à
  vérifier ».

## Résultat visible dans OpenCRVS

Connexion registraire (`k.mweene`) → file **Notifications** → dossier
pré-rempli : identité de l'enfant, lieu de naissance complet, parents avec
nationalités, scan joint, commentaire exhaustif. L'officier complète les
quelques champs que l'acte ne contient pas (email de l'informant, type de
pièce d'identité, raison de l'enregistrement tardif) et valide.

## Migration vers une vraie instance (quand décidé)

Il suffit de créer un client d'intégration « Event notification » sur
l'instance cible et de changer **4 variables** dans `.env` :
`OPENCRVS_AUTH_URL`, `OPENCRVS_GATEWAY_URL`, `OPENCRVS_CLIENT_ID/SECRET`
(+ l'UUID du bureau destinataire). Aucun changement de code.

# OCR d'actes d'état civil → OpenCRVS

Numériser un acte de naissance africain et en pré-remplir une déclaration dans
**OpenCRVS**, pour que l'officier d'état civil **vérifie** au lieu de
**ressaisir**.

Le système lit un scan (photo, image, PDF), en extrait les champs avec un
modèle vision-langage, les valide, leur attribue un score de confiance, puis
alimente le registre civil numérique — soit par l'API de notification, soit
directement **à l'intérieur du formulaire de déclaration OpenCRVS**.

---

## Sommaire

- [Ce que fait le projet](#ce-que-fait-le-projet)
- [Principe directeur : le gate d'honnêteté](#principe-directeur--le-gate-dhonnêteté)
- [Démarrage rapide](#démarrage-rapide)
- [Le pipeline d'extraction](#le-pipeline-dextraction)
- [Packs pays](#packs-pays)
- [Intégration OpenCRVS](#intégration-opencrvs)
- [Évaluation](#évaluation)
- [Structure du dépôt](#structure-du-dépôt)
- [Exploitation de la plateforme locale](#exploitation-de-la-plateforme-locale)
- [Limites connues](#limites-connues)

---

## Ce que fait le projet

Trois briques indépendantes mais complémentaires :

| Brique | Rôle |
|---|---|
| **Pipeline OCR** (`pipeline/`, `run_pipeline.py`) | scan → champs structurés + score de confiance par champ |
| **Application web** (`review/`) | dépôt des scans (glisser-déposer ou QR téléphone), suivi, écran de correction |
| **Intégration OpenCRVS** (`pipeline/opencrvs_export.py`, `fork/ocr.ts`) | déclaration pré-remplie, en API ou directement dans le formulaire |

Chiffres mesurés : **27 packs pays**, ~40 à 90 s de traitement par acte,
~7 champs OpenCRVS pré-remplis par document en moyenne. Voir
[Évaluation](#évaluation) pour la méthode et les limites de ces chiffres.

---

## Principe directeur : le gate d'honnêteté

À chaque étage, le système préfère **ne rien affirmer** plutôt qu'affirmer faux :

- **Localisation** — si le gabarit ne colle pas (couverture < 0,6), bascule sur
  une localisation par le modèle plutôt que de dessiner des cadres « confiants
  mais faux ».
- **Valeurs peu sûres** — en dessous du seuil de confiance 0,6, la valeur est
  quand même pré-remplie mais explicitement marquée **« à vérifier »** dans le
  commentaire de revue. Jamais présentée comme fiable.
- **Nationalité ambiguë** — « CONGOLAISE » (deux Congo) n'est jamais tranchée
  automatiquement ; la valeur brute reste visible pour l'officier.
- **Lieu d'accouchement** — la catégorie (hôpital / domicile / autre) n'est
  jamais devinée : l'acte ne la précise généralement pas.
- **Nationalité et lieu de naissance sont distincts** — la nationalité n'est
  jamais déduite d'un lieu de naissance. Un acte du corpus le démontre : le père
  y est né à Dakar mais l'acte précise « Citoyen Français de Naissance ».

---

## Démarrage rapide

### Prérequis

- Python 3.12 et un environnement virtuel (`.venv`)
- Une clé API Gemini dans `.env` (`GEMINI_API_KEY`)
- Pour l'intégration OpenCRVS : Docker Desktop + WSL (voir
  [`OPENCRVS_LOCAL.md`](OPENCRVS_LOCAL.md))

```bash
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt
cp .env.example .env      # puis renseigner GEMINI_API_KEY
```

### Traiter un acte en ligne de commande

```bash
.venv/Scripts/python run_pipeline.py samples/tn_extrait_1981.jpg --backend gemini
```

Produit `runs/<doc>/report.json` (champs + scores), `field_boxes.png`
(visualisation des zones détectées) et `original.<ext>` (le scan conservé pour
être joint à la déclaration).

### Lancer l'application web

```bash
.venv/Scripts/python -m uvicorn review.app:app --port 8000
```

- `http://localhost:8000` — dépôt des scans, QR pour photographier au téléphone
- `http://localhost:8000/review` — écran de correction

### Lancer la plateforme complète (OpenCRVS + application)

```bash
powershell -ExecutionPolicy Bypass -File start-opencrvs.ps1
```

Démarre les conteneurs, les 14 microservices OpenCRVS et l'application OCR,
affiche un tableau de bord en direct, répare les services défaillants, puis
vérifie l'intégration. Se termine par « TOUT EST VERT ».

> Les services tournent **fenêtre masquée** (`tools/run_hidden.vbs`). Sans cela,
> chaque tâche planifiée ouvrait sa propre console — une vingtaine de terminaux
> par démarrage, dont la fermeture accidentelle tuait le service hébergé. Si les
> tâches sont un jour recréées, réappliquer avec
> `tools/hide_service_windows.ps1`.

---

## Le pipeline d'extraction

```
scan (image ou PDF)
   │
[1] prétraitement    redressement · mise à l'échelle · binarisation
   │                 le scan d'origine est conservé (pièce jointe OpenCRVS)
[2] détection pays   lecture de l'en-tête → pack pays, sinon pack générique
   │
[3] localisation     gabarit (rapide) ; si couverture < 0,6 → localisation VLM
   │
[4] extraction       passe 1 : page entière ─┐
   │                 passe 2 : recadrages    ├─ consensus entre les deux
   │                 (lots de 5, 4 workers)  ─┘
[5] validation       dates en toutes lettres → ISO · énumérations · lieux
   │                 score par champ → auto-accepté ou à relire
   ▼
runs/<doc>/report.json
```

L'accord entre les deux passes indépendantes sert à la fois de signal de
confiance et de mesure interne de fiabilité.

**Backends** — `--backend gemini` (par défaut), `ollama` ou `openai`. La bascule
vers un modèle hébergé localement ne demande aucun changement de code : c'est le
chemin prévu pour la production, où des données d'état civil ne doivent pas
transiter par une API tierce.

---

## Packs pays

27 pays + un pack générique, dans `config/countries/<code>/` :

- `schema.json` — champs attendus sur ce type d'acte (nom, libellé, type)
- `places.json` — lexique de lieux, qui oriente l'OCR vers les bonnes graphies

Algérie, Angola, Bénin, Cameroun, Cap-Vert, Congo-Brazzaville, RD Congo,
Côte d'Ivoire, Égypte, Gabon, Guinée, Kenya, Liban, Libéria, Madagascar, Mali,
Maroc, Maurice, Mauritanie, Nigéria, Rwanda, Sénégal, Seychelles, Sierra Leone,
Afrique du Sud, Togo, Tunisie.

Chaque pack nomme ses champs dans son propre vocabulaire (`enfant_nom` ici,
`nom` + `prenoms` ailleurs, `pere_nom_complet` autre part) ; une table d'alias
dans `pipeline/opencrvs_export.py` les ramène tous vers les identifiants
OpenCRVS.

---

## Intégration OpenCRVS

**Aucune modification du code d'OpenCRVS.** Tout passe par l'API officielle et
par le dépôt de configuration pays (fork).

### Voie 1 — API Event Notification

Le document traité part vers la file *Notifications* du bureau d'état civil,
déclaration déjà pré-remplie et scan joint.

```bash
.venv/Scripts/python tools/send_to_opencrvs.py runs/<doc> [--dry-run]
```

```
POST {auth}/token                          client_credentials
POST {gateway}/events/events               création de l'événement
POST {gateway}/upload                      scan → MinIO
POST {gateway}/events/events/notifications déclaration + pièce jointe
```

### Voie 2 — Pré-remplissage dans le formulaire

Un panneau ajouté à la page « Child's details » permet de déposer le scan
**sans quitter OpenCRVS** : les champs du formulaire se remplissent seuls, sur
toutes les pages (enfant, parents, déclarant), et l'officier continue vers la
page de relecture native.

```
child.ocr-scan (FILE)  → OpenCRVS stocke le scan dans son propre MinIO
        ↓ déclenche
child.ocr-fetch (HTTP) → POST le chemin MinIO au service OCR
        ↓ réponse
chaque champ lit sa valeur via `parent` + `value`
```

Le code du panneau est dans [`fork/ocr.ts`](fork/ocr.ts), déployé vers le fork
countryconfig par `tools/deploy_fork_ocr.sh`.

Deux contraintes de la plateforme ont façonné cette conception :

- `FieldType.HTTP` ne transmet que du JSON, jamais des octets de fichier — d'où
  le passage par le stockage d'OpenCRVS et l'envoi d'un **chemin**.
- Une référence `value` est résolue en découpant le chemin sur les points et en
  descendant dans le JSON. La réponse expose donc une branche `fields`
  réellement imbriquée ; la branche `declaration` reste plate pour l'API.
- Un champ ne se synchronise que si sa propriété **`parent`** déclare la source.
  `value` seul est inerte.

### Migration vers une autre instance

Créer un client d'intégration « Event notification » sur l'instance cible, puis
changer quatre variables dans `.env` :

```
OPENCRVS_AUTH_URL · OPENCRVS_GATEWAY_URL · OPENCRVS_CLIENT_ID · OPENCRVS_CLIENT_SECRET
```

(plus `OPENCRVS_LOCATION_ID`, le bureau destinataire). Aucun changement de code.

---

## Évaluation

Deux questions distinctes, mesurées séparément.

### Justesse — contre des valeurs de référence

```bash
.venv/Scripts/python tools/evaluate_quality.py
```

Mesure ANLS, taux d'erreur caractère et mot, précision / rappel / F1 par champ,
taux d'hallucination, conformité au schéma et exactitude du découpage
prénom / nom, contre les références de `eval/ground_truth.json`.

### Rendement — sans référence, sur tout le lot

```bash
.venv/Scripts/python tools/evaluate_batch.py
```

Mesure la part de champs auto-acceptés, le nombre de champs OpenCRVS
pré-remplis et la répartition des scores de confiance.

### Rapport

```bash
.venv/Scripts/python tools/build_eval_report.py   # → rapport_evaluation.pdf
```

Le rapport est généré **à partir des sorties des harnais**, sans valeur saisie à
la main : relancer les mesures et le régénérer suffit à le tenir à jour.

> **Portée des chiffres.** Les références ont été transcrites dans le cadre du
> projet, non par un annotateur indépendant : une erreur de lecture partagée par
> le pipeline et par la transcription ne serait pas détectée. L'échantillon est
> petit. Ces résultats montrent que le système traite correctement ces
> documents-là — ils ne prouvent pas une absence d'erreurs en général.

---

## Structure du dépôt

```
pipeline/            le pipeline (prétraitement, localisation, extraction,
                     validation, confiance, export OpenCRVS)
review/              application web FastAPI (dépôt, QR, correction, envoi)
config/countries/    27 packs pays + pack générique
fork/ocr.ts          panneau de numérisation intégré au formulaire OpenCRVS
tools/               harnais d'évaluation, déploiement du fork, exploitation
eval/                valeurs de référence et métriques calculées
tests/               tests hors-ligne du mapping OpenCRVS
samples/             corpus d'actes réels
runs/                sorties par document (report.json, crops, scan d'origine)
notes-superviseur/   notes de synthèse et métriques par document
```

Documents de référence : [`HANDOFF.md`](HANDOFF.md) (état complet du projet et
pièges d'exploitation), [`OPENCRVS_LOCAL.md`](OPENCRVS_LOCAL.md) (plateforme
locale au quotidien).

---

## Exploitation de la plateforme locale

Une instance OpenCRVS complète (v1.9.14) tourne en local : distro WSL dédiée,
Docker pour les dépendances (MongoDB, Elasticsearch, PostgreSQL, MinIO, Redis,
InfluxDB), et une tâche planifiée Windows par microservice.

| Utilisateur | Mot de passe | Rôle |
|---|---|---|
| `k.mweene` | `test` | Officier local — voit les notifications OCR |
| `j.campbell` | `test` | Admin système — menu Configuration → Integrations |

Code 2FA : `000000`. Détails, ports et dépannage dans
[`OPENCRVS_LOCAL.md`](OPENCRVS_LOCAL.md).

**Piège principal** : un arrêt brutal du PC fait revenir MongoDB en arrière, ce
qui supprime le client d'intégration et change les identifiants de lieux.
`start-opencrvs.ps1` détecte les deux au démarrage et resynchronise ce qu'il
peut. Faire `wsl --shutdown` avant d'éteindre évite le problème.

---

## Limites connues

- **Ordre prénom / nom** — lorsqu'un acte écrit le nom de famille en premier et
  tout en majuscules (Bénin, Nigéria), le découpage des noms de parents peut
  être inversé. Le nom est correctement lu ; c'est sa répartition entre les deux
  champs qui est erronée. Correctifs envisagés : exploiter le patronyme de
  l'enfant lorsqu'il apparaît chez un parent, et déclarer l'ordre des noms dans
  le pack pays.
- **Actes manuscrits** — la reconnaissance d'écriture manuscrite est un problème
  distinct et nettement plus difficile. Ces documents sont traités par le
  pipeline mais exclus des métriques, qu'ils fausseraient.
- **Quotas** — le palier gratuit de l'API Gemini (~250 requêtes/jour/clé, avec
  rotation automatique) suffit à la démonstration, pas à la production.
- **Confidentialité** — en production, les données d'état civil ne doivent pas
  transiter par une API tierce : basculer sur `--backend ollama` avec un modèle
  hébergé localement.
- **Envois non idempotents** — renvoyer un document par l'API de notification
  crée un doublon dans la file. Correctif prévu : identifiant de transaction
  dérivé du hachage du fichier.
- **Lieux** — les lieux réels ne peuvent pas être rattachés aux zones
  administratives internes tant que l'on travaille sur l'instance de
  démonstration ; une adresse internationale complète est utilisée en attendant.

# Actes OCR — extraction d'actes d'état civil (multi-pays)

A local-first pipeline that replicates the handwritingocr.com workflow for
Gabonese birth certificates: image cleanup, **exact field localization**,
two-pass VLM extraction with consensus, French-specific validation, and a
human-in-the-loop review UI whose corrections become fine-tuning data.

```
 scan.png
    │
 [1] preprocess      illumination fix · CLAHE · denoise · deskew · upscale
    │                (optional --destamp: suppress blue/green stamp ink)
 [2] locate          printed labels OCR'd (tesseract fra) → fuzzy-matched to a
    │                layout template → per-field bounding boxes + crops
    │                → field_boxes.png overlay for QA
 [3] extract         PASS 1: whole page + full schema  ─┐
    │                PASS 2: each field crop            ├─ consensus
    │                                                   ─┘
 [4] validate        French date-in-words parser · CNIN↔birthdate cross-check
    │                chronology · gazetteer of Gabonese places · enums
 [5] confidence      score = model + agreement + validation → route:
    │                auto-accept / human review
 [6] review UI       crop-next-to-value verification, worst first;
                     every correction appended to data/corrections.jsonl
                     → export.py sft → fine-tune the local VLM → repeat
```

## Country packs

The pipeline is country-agnostic; everything country-specific lives in
`config/countries/<code>/`:

```
config/countries/          layout style        country-specific analysis
  ga/  Gabon               form (manuscrit)    CNIN↔date-de-naissance cross-check
  tn/  Tunisie             form (table)        registry-year↔declaration check
  bj/  Bénin               form (volet)        RED-reference-year check; late-
                                               declaration (jugement supplétif) warn
  rw/  Rwanda              form (bilingue FR/  acte-n°/year check (170/2013 ↔ l'an
       manuscrit)          kinyarwanda)        deux mille treize)
  cg/  Congo-Brazzaville   lines               registre/année check; '**' = vide
  ci/  Côte d'Ivoire       NARRATIVE (====)    reference-year check; prose sections
  mg/  Madagascar          NARRATIVE           registre-year; dates de délivrance/
                                               traduction en toutes lettres
  cv/  Cap-Vert            form (traduction)   reference-year (n° 348/03-09-1973);
                                               '***' = occulté
  tg/  Togo                form (volet souche) année/acte check; '/' = vide
  dz/  Algérie             form (pointillés)   date-en-marge ↔ date-de-naissance
  ao/  Angola              NARRATIVE           n° d'acte EN LETTRES ↔ n° en marge
                           (traduction)        (Deux mille quatre cents vingt-sept ↔ 2427)
  cm/  Cameroun            form (bilingue FR/  'vers <année>' toléré; section père
                           EN, manuscrit)      souvent vide
  mu/  Maurice             form (bilingue EN/  le NID embarque JJMMAA de la date de
                           FR, dactylographié) naissance (S230591... ↔ 23/05/1991)
  gn/  Guinée              form (machine à     valeurs 'ETIQUETTE :VALEUR';
                           écrire)             double certification
  za/  Afrique du Sud      form numéroté       le n° d'identité embarque AAMMJJ
                           (traduction)        (640916... ↔ 1964/09/16); 'non stipulé'
  cd/  RD Congo            form (manuscrit,    acte-n°/année check (4049/2023 ↔ l'an
                           filigrane, tampons) deux mille vingt-trois); détection par
                                               labels (Chefferie, Bureau Principal)
  sn/  Sénégal             form (manuscrit,    TROIS paires lettres↔chiffres (année,
                           cases)              n° registre, n° jugement); valeurs
                                               au-dessus des légendes
  eg/  Égypte              form (traduction,   n° NATIONAL embarque siècle+AAMMJJ
                           original arabe)     (2 761010... ↔ 10/10/1976)
  ke/  Kenya               form (traduction)   n° d'acte NNNNNNN/AAAA ↔ année d'enreg.
  lr/  Libéria             form (traduction)   n° d'enregistrement embarque l'année
  ng/  Nigéria             form (traduction)   NPC/... <année> ↔ année d'enregistrement
  sc/  Seychelles          TABLE paysage       orientation 90° corrigée par vote OCR;
                           (traduction)        extraction par bande de tableau
  sl/  Sierra Leone        form (traduction)   '---' = null; registre n°/page/volume
  lb/  Liban               table numérotée     rubriques 1-16; Religion/Rite
                           1-16 (traduction)
  ma/  Maroc               form + marge        dates HÉGIRIENNES + grégoriennes;
                                               date-marge ↔ naissance; mentions
                                               marginales (mariages/divorces)
  ml/  Mali                form numéroté 1-26  'VERS <année>'; réf. jugement supplétif
                                               dans la rubrique déclarant
  mr/  Mauritanie          form sécurisé       cohérence inter-cadres: prénom-du-père
                           (RNP, bilingue)     (Enfant) ↔ prénom (Père)
  zz/  Générique           —                   pays non reconnu: schéma universel,
                                               extraction page seule, tout en revue
```

Two layout families are supported by the same machinery. **Form layouts**
get per-field boxes from label anchors. **Narrative layouts** (prose
paragraphs) get *section bands* instead — "Ayant pour père → Et pour mère"
becomes one crop mapped to several schema fields — and each pack's
`prompt_hint` teaches the model how that country's prose is structured. The
French dates-in-words parser, chronology checks and gazetteer validation are
shared everywhere.

Each pack contains `country.json` (name, header keywords for auto-detection,
which validators apply), `schema.json` (the logical fields), `templates/`
(layout anchors + geometry) and `places.json` (gazetteer). By default
`--country auto` reads the printed header ("REPUBLIQUE TUNISIENNE",
"République Gabonaise", ...) and picks the pack; force one with
`--country tn`. Adding a country is adding a directory — probe one clean
specimen with `tools/probe_labels.py`, write the template from the output,
list the fields, done. The French date-in-words parser, the two-pass
consensus, confidence routing, the review UI and the fine-tuning flywheel
are shared across all packs.

## Quickstart (Windows)

```bat
:: 1. Python deps (Python 3.10+)
py -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt

:: 2. Tesseract (for field localization, NOT for the handwriting itself)
::    Install the UB Mannheim build: https://github.com/UB-Mannheim/tesseract/wiki
::    During setup tick "French" under Additional language data, or copy
::    fra.traineddata into ...\Tesseract-OCR\tessdata
set TESSERACT_CMD=C:\Program Files\Tesseract-OCR\tesseract.exe

:: 3. First run — stages 1-2 only, no model needed. Inspect the overlay!
py run_pipeline.py samples\volet_mere_2002.png --backend none
::    → runs\volet_mere_2002\field_boxes.png  (green = anchor found,
::      orange = interpolated) and runs\...\crops\*.png

:: 4. Full run with a model (see backend matrix below)
py run_pipeline.py samples\volet_mere_2002.png --backend ollama --model glm-ocr
py run_pipeline.py samples\volet_mere_2002.png --backend gemini
py run_pipeline.py samples\tn_extrait_1981.jpg --backend gemini   :: country auto-detected

:: 5. Web app: upload (drag-drop, PDF ok, QR pour téléphone) + review
uvicorn review.app:app --reload    →  http://localhost:8000
```

Linux/macOS: same commands with `python3` and `apt install tesseract-ocr
tesseract-ocr-fra` (or `brew install tesseract tesseract-lang`).

The repo ships with the three sample documents already processed under
`runs/`, so the review UI has something to show the moment you start it —
`volet_mere_2002` was run end-to-end with the mock backend
(`--backend mock --fixture fixtures/volet_mere_2002.json`).

## Interface web & déploiement

`uvicorn review.app:app` sert trois pages :

| page | rôle |
|------|------|
| `/` | dépôt : glisser-déposer (PNG/JPG/TIFF/WEBP/BMP/**PDF**, page 1 traitée), QR code téléphone, liste des documents avec progression en direct |
| `/m/<session>` | page téléphone ouverte via le QR : **prendre une photo** ou choisir un fichier — le document part directement dans la file de traitement de votre PC |
| `/review` | bureau de vérification (corrections → `data/corrections.jsonl`) |

En local, le QR encode automatiquement l'adresse LAN (le téléphone doit être
sur le même Wi-Fi). Déployée, l'application est accessible de partout.

**Déployer (backend Gemini uniquement) :**

```bash
# Docker n'importe où
docker build -t gabon-ocr .
docker run -p 8000:8000 -e GEMINI_API_KEY=... -e APP_PASSWORD=... gabon-ocr

# ou Render en un clic : pousser le repo sur GitHub puis
# New → Blueprint (render.yaml est fourni) ; renseigner GEMINI_API_KEY.
```

Variables d'environnement : `GEMINI_API_KEY` (obligatoire),
`APP_PASSWORD` (protège l'UI par mot de passe — les URLs téléphone restent
accessibles via leur session à usage unique), `PUBLIC_BASE_URL` (origine
https à mettre dans le QR derrière un proxy), `PIPELINE_BACKEND`
(`gemini` par défaut ; en local vous pouvez mettre `ollama`).

Le conteneur embarque tesseract + le `tessdata/` français du repo ; aucune
configuration système n'est nécessaire.

## Backend matrix

| backend  | flag                                   | notes |
|----------|----------------------------------------|-------|
| Ollama   | `--backend ollama --model <tag>`       | needs a **vision** model (see below) |
| Gemini   | `--backend gemini [--model id]`        | set `GEMINI_API_KEY` (aistudio.google.com/apikey); default `gemini-2.5-flash`, JSON output enforced |
| OpenAI-compatible | `--backend openai --base-url http://localhost:8000/v1 --model <id>` | vLLM / LM Studio / llama.cpp server — the serious local-serving path |
| mock     | `--backend mock --fixture <json>`      | no GPU: exercises validation/scoring/review |
| none     | `--backend none`                       | stages 1–2 only: check localization quality |

### Which of your local models can do this?

Only **vision** models can read an image. From a typical `ollama list`:

| model              | vision? | verdict for this task |
|--------------------|---------|------------------------|
| `glm-ocr`          | ✅      | best of the already-installed options — OCR-tuned VLM, start here |
| `llava`            | ✅      | works, but 2023-era; expect weak French cursive accuracy |
| `qwen2.5:7b`       | ❌ text-only | cannot see images — will not work |
| `llama3.2` (2 GB)  | ❌ text-only | the vision variant is a different, larger tag |
| embed models       | ❌      | embeddings only |

Recommended upgrade: `ollama pull qwen3-vl` (Qwen3-VL 8B, ~6.1 GB, also
available as `qwen3-vl:4b` / `qwen3-vl:2b` for smaller GPUs). It is the
strongest open-weights family for handwriting/OCR at this size and the one
you would later fine-tune with the corrections this pipeline collects.

A pragmatic strategy: **develop and measure with `--backend gemini`**
(fast, strong, no GPU pressure), then switch the same pipeline to the local
model and close the gap with fine-tuning. The pipeline code is identical
across backends.

## Robustness on messy real-world pages

Localization defends itself in three ways (all in `pipeline/locate.py`):

* **Multi-form pages** — photocopies often carry the filled volet next to an
  empty duplicate and a mentions panel, so every label appears 4+ times.
  Anchor candidates are clustered into x-columns and only the strongest
  column (most distinct, best-scoring labels) is kept.
* **Order enforcement** — matched anchors must respect the template's
  vertical order (longest-increasing-subsequence filter); stray or stolen
  matches are dropped and re-interpolated.
* **Reliability gate** — if too few anchors are found, or their positions
  don't fit the template's nominal layout (median residual > 2.5× label
  height), the run is marked `reliable: false`: the overlay gets a red
  banner, the crop pass is skipped, extraction runs on the whole page only,
  and **every field is routed to review**. The system says "I could not
  localize" instead of emitting wrong boxes.

Practical floor: printed labels need to be roughly ≥ 20 px tall for the
anchor pass. Scan at 300 DPI (or crop the filled form out of multi-form
photocopies). Below that floor the VLM page-pass fallback still extracts —
modern VLMs read low-resolution text far better than tesseract — you just
lose the crop pass and its consensus signal, so expect more review work.

### Robustesse sur de nouveaux échantillons

La localisation par gabarit est un ACCÉLÉRATEUR de précision, pas une
dépendance: la passe page du VLM n'utilise aucun gabarit. Les couches, de la
plus spécifique à la plus générale:

1. document connu, layout connu → ancres floues + occurrences + filtre
   d'ordre + interpolation affine absorbent bruit OCR, tampons et dérives;
2. nouveau millésime d'un layout connu → si le fit n'est pas fiable, la
   passe crops est coupée, extraction page seule, tout part en revue —
   jamais de boîtes silencieusement fausses. Calibrer le millésime =
   `tools/probe_labels.py` + un fichier JSON;
3. nouveau pays non reconnu → pack générique `zz`: schéma universel,
   indication de prudence au modèle, revue à 100 %.

Le composant réellement adaptatif est le VLM; le déterminisme ne borne que
la localisation. Pour une localisation adaptative sans gabarit (layouts
inédits en masse), un locator « VLM-grounded » (le modèle émet lui-même les
boîtes) peut être branché comme troisième stratégie sans toucher au reste.

### Multi-page documents

The pipeline processes one page image per run. For multi-page PDFs (e.g. the
Cape-Verdean translation whose verso carries the consular certification),
rasterize each page (`pdftoppm -png -r 300 file.pdf page`) and run the pages
separately; the verso usually only needs the page-level pass.

## The 95 % question

No model reads degraded 1990s cursive at 95 % raw. The target is reached as
a **system**:

1. preprocessing recovers faint ink (stage 1);
2. localization means the model reads *the right strip of paper* — a whole
   class of "right value, wrong line" errors disappears (stage 2);
3. two independent passes must agree, or the field is flagged (stage 3);
4. validators exploit the document's redundancy — e.g. the C.N.I. line often
   embeds the holder's birth date: on the shipped 2002 sample the pipeline
   flags `mere_cnin` because the CNIN says 17.10.1984 while the declared
   birth date is 16.10.1984 (stage 4);
5. everything not proven is routed to a human whose correction costs seconds
   (stages 5–6);
6. corrections accumulate in `data/corrections.jsonl`; `py export.py sft`
   turns them into training samples; a LoRA fine-tune of the local VLM on a
   few hundred of them measurably lifts accuracy on *your* form family, which
   shrinks the review queue — the same flywheel commercial services run.

Tune the routing thresholds in `pipeline/confidence.py` (`AUTO_ACCEPT`,
`LOW`) against your own tolerance: stricter = more review, fewer errors.

## Adding a new layout (e.g. the 1991 full-page acte)

The two "volet" samples share one printed template, covered by
`config/templates/volet_v1.json`. The 1991 A5 acte is a different layout and
needs its own template (10-minute job):

```bat
py run_pipeline.py samples\gabon_p4.png --backend none
py tools\probe_labels.py runs\gabon_p4\enhanced_gray.png
```

Copy the printed-label lines it finds into a new
`config/templates/acte_a5_v1.json` (same shape as `volet_v1.json`), set each
anchor's `rel_y` from the printed column, choose a `detect_keyword` unique to
that layout, and list the fields with `right_of` / `band` geometry. The
locator then auto-selects the template per document.

### Multi-form carbon sheets

Some certified copies are carbon sheets carrying SEVERAL copies of the same
printed form side by side (a filled volet next to a blank duplicate and a
mentions panel). Since the printed labels are identical on every copy, naive
anchor matching gets contaminated across panels. The locator handles this:
label hits are clustered into columns, and when more than one column looks
like a form, the pipeline keeps the column containing the most ink — the
filled copy — and clamps all field geometry to it (`multi_form_slab` in
locate.json). `samples/synthetic_double.png` is the regression test for this.
If localization still can't establish a trustworthy fit, the run degrades
gracefully: `reliable=false`, the crop pass is skipped, extraction is
page-only and every field is routed to review — never silently wrong boxes.

For heavily stamped documents like that one, add `--destamp` — see
`demo/destamp_before_after.png` for the effect of suppressing saturated
blue/green stamp ink before reading.

## Repo map

```
run_pipeline.py            CLI: all stages for one document
pipeline/preprocess.py     stage 1  image cleanup
pipeline/locate.py         stage 2  anchors → exact field boxes + crops
pipeline/extract.py        stage 3  two-pass VLM + consensus
pipeline/validate.py       stage 4  dates-in-words parser, CNIN check, gazetteer
pipeline/confidence.py     stage 5  scoring + routing
pipeline/vlm_client.py     backends: ollama / openai-compat / gemini / mock
review/app.py + static/    stage 6  human review UI (FastAPI)
export.py                  golden CSV + fine-tuning JSONL
tools/probe_labels.py      calibrate templates for new layouts
config/schema.json         the 25 logical fields
config/templates/          layout templates (anchors + geometry)
fixtures/                  mock model outputs for GPU-less testing
tests/test_validate.py     date parser / gazetteer tests
samples/                   the three source scans
runs/                      per-document outputs (pre-generated for the demo)
```

## Privacy note

These documents carry real personal data. Keep processing local (Ollama /
vLLM) for production; if you use a cloud backend for development, use test
documents or documents you are authorized to process, and prune `runs/` and
`data/` accordingly.

# 1. Pipeline OCR

`run_pipeline.py <scan> --backend gemini` → `runs/<doc>/report.json`

## Étapes

1. **Prétraitement** : redressement (deskew), mise à l'échelle, binarisation,
   variantes couleur/gris améliorées. PDF accepté (première page).
   Le scan brut est conservé (`original.<ext>`) pour la pièce jointe OpenCRVS.
2. **Détection du pays** : lecture de l'en-tête → choix du pack pays
   (`config/countries/<code>/`), fallback générique si inconnu.
3. **Localisation des champs** : d'abord par **gabarit** (rapide, ancres
   textuelles) ; si la couverture des champs < 0.6 (« gate d'honnêteté »),
   bascule sur **grounding VLM** (le modèle localise lui-même les zones).
   Jamais de localisation « confiante mais fausse ».
4. **Extraction** : double passe — page entière + recadrages par champ,
   envoyés au VLM **par lots de 5 images, 4 workers en parallèle, réflexion
   du modèle bridée** → c'est ce qui a fait passer le temps de traitement
   de ~10 min à ~35–50 s par document.
5. **Validation & score** : normalisation (dates ISO, enums), score de
   confiance par champ, statut auto-accepté / à relire.

## Packs pays (27 + générique)

Chaque pack contient :
- `schema.json` — les champs attendus sur ce type d'acte (noms, libellés FR,
  types : date, nom, lieu, enum…) ;
- `places.json` — lexique de lieux du pays (biaise l'OCR vers les bonnes
  orthographes) ;
- gabarits de localisation le cas échéant.

Pays couverts : Algérie, Angola, Bénin, Cameroun, Cap-Vert, Congo-B., RD
Congo, Côte d'Ivoire, Égypte, Gabon, Guinée, Kenya, Liban, Libéria,
Madagascar, Mali, Maroc, Maurice, Mauritanie, Nigéria, Rwanda, Sénégal,
Seychelles, Sierra Leone, Afrique du Sud, Togo, Tunisie.

## Backends VLM

- **Gemini** (par défaut) : clés en rotation automatique sur quota (free
  tier) ; 429 = quota, 403 = facturation.
- `--backend ollama` / `--backend openai` déjà supportés → **bascule vers un
  VLM local/souverain sans changer le pipeline** (important : en production,
  les données d'état civil ne doivent pas transiter par une API tierce).

## Sorties par document (`runs/<doc>/`)

- `report.json` — champs + valeurs + scores (l'entrée du mapping OpenCRVS)
- `field_boxes.png` — visualisation des zones détectées
- `original.<ext>` — le scan brut (pièce jointe OpenCRVS)
- `place_lookup.json` — cache de la résolution de lieux
- `opencrvs.json` — trace du dernier envoi (event id, champs pré-remplis)

"""OCR -> OpenCRVS: turn a pipeline report into a V2 Event Notification.

OpenCRVS (1.9, V2 events) accepts *incomplete, prefilled* birth declarations
from trusted systems — designed for hospital notifications, and a perfect fit
for scanned-register OCR: send only what we're confident about, the registrar
completes the rest inside OpenCRVS. Three calls, documented by the Postman
collection shipped in the countryconfig repo (Event Notification - v1.9.0):

    POST {auth}/token?client_id&client_secret&grant_type=client_credentials
    POST {gateway}/events/events                 {type, transactionId}
    POST {gateway}/events/events/notifications   {eventId, declaration, ...}

Declaration keys are the V2 form field ids (countryconfig
src/form/v2/birth/forms/pages/*.ts). Every format-valid value is prefilled;
values under the confidence threshold are additionally flagged "à vérifier"
in the annotation review comment, and unmappable values (free-text
birthplaces etc.) are comment-only — the registrar always sees what the
OCR read and how sure it was.

Config via environment / .env:
    OPENCRVS_AUTH_URL      e.g. https://auth.<domain>       (token endpoint)
    OPENCRVS_GATEWAY_URL   e.g. https://gateway.<domain>    (events endpoints)
    OPENCRVS_CLIENT_ID     integration client (admin UI -> Integrations ->
    OPENCRVS_CLIENT_SECRET  Event notification)
    OPENCRVS_LOCATION_ID   office/district UUID for createdAtLocation
"""
from __future__ import annotations

import json
import os
import re
import unicodedata
import uuid
from pathlib import Path

from .vlm_client import _post

# below this score a value is still prefilled but flagged "à vérifier" in the
# review comment (matches confidence.LOW)
DEFAULT_THRESHOLD = 0.6

_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _strip_accents(s: str) -> str:
    s = unicodedata.normalize("NFKD", s)
    return "".join(c for c in s if not unicodedata.combining(c))


def split_name(full: str) -> dict:
    """'Yamousso THIAM' -> {firstname: 'Yamousso', surname: 'THIAM'}.

    Francophone civil records write the family name in UPPERCASE; tokens that
    are fully uppercase (2+ letters) are the surname, the rest the firstname.
    Falls back to last-token-is-surname when nothing is uppercased.
    """
    tokens = [t for t in full.replace(",", " ").split() if t]
    if not tokens:
        return {"firstname": "", "surname": ""}
    upper = [t for t in tokens if len(t) >= 2 and t.isupper()]
    lower = [t for t in tokens if t not in upper]
    if upper and lower:
        return {"firstname": " ".join(lower), "surname": " ".join(upper)}
    if len(tokens) == 1:
        # a lone token is a given name unless it is written in the uppercase
        # reserved for family names — an act body often names the child by
        # first name only ("de Yamousso du sexe Féminin"), and calling that a
        # surname leaves the required firstname empty for no reason
        token = tokens[0]
        if len(token) >= 2 and token.isupper():
            return {"firstname": "", "surname": token}
        return {"firstname": token, "surname": ""}
    return {"firstname": " ".join(tokens[:-1]), "surname": tokens[-1]}


def map_gender(value: str) -> str | None:
    v = _strip_accents(value).strip().lower()
    if v in ("masculin", "m", "male", "garcon"):
        return "male"
    if v in ("feminin", "f", "female", "fille"):
        return "female"
    return None


# French nationality adjective stem -> ISO3 country code (value format of the
# V2 COUNTRY field type). Stems match both genders (TUNISIEN(NE)). CONGOLAIS
# is ambiguous (COG/COD) and deliberately absent — it stays in the comment.
_NATIONALITY_STEMS = [
    ("TUNISIEN", "TUN"), ("MAROCAIN", "MAR"), ("ALGERIEN", "DZA"),
    ("SENEGALAIS", "SEN"), ("MALIEN", "MLI"), ("IVOIRIEN", "CIV"),
    ("CAMEROUNAIS", "CMR"), ("GABONAIS", "GAB"), ("GUINEEN", "GIN"),
    ("BENINOIS", "BEN"), ("TOGOLAIS", "TGO"), ("NIGERIAN", "NGA"),
    ("NIGERIEN", "NER"), ("KENYAN", "KEN"), ("RWANDAIS", "RWA"),
    ("MAURITANIEN", "MRT"), ("MAURICIEN", "MUS"), ("MALGACHE", "MDG"),
    ("EGYPTIEN", "EGY"), ("LIBANAIS", "LBN"), ("ANGOLAIS", "AGO"),
    ("CAPVERDIEN", "CPV"), ("SEYCHELLOIS", "SYC"), ("SIERRALEONAIS", "SLE"),
    ("LIBERIEN", "LBR"), ("SUDAFRICAIN", "ZAF"), ("BURKINAB", "BFA"),
    ("TCHADIEN", "TCD"), ("CENTRAFRICAIN", "CAF"), ("FRANCAIS", "FRA"),
    ("COMORIEN", "COM"), ("DJIBOUTIEN", "DJI"), ("BURUNDAIS", "BDI"),
    ("ZAMBIEN", "ZMB"), ("GHANEEN", "GHA"), ("GAMBIEN", "GMB"),
]


def map_nationality(value: str) -> str | None:
    """'TUNISIENNE' / 'Citoyen Français de Naissance' -> ISO3 country code.

    Matched per word rather than on the whole string: acts phrase nationality
    freely ("Citoyen Français de Naissance"), so the adjective is rarely the
    first word. Each word must *start* with a stem — a plain substring search
    would read "Somalienne" as Malian.
    """
    words = re.split(r"[^A-Z]+", _strip_accents(value).upper())
    for word in words:
        if not word:
            continue
        for stem, code in _NATIONALITY_STEMS:
            if word.startswith(stem):
                return code
    return None


def map_informant_relation(value: str) -> str | None:
    v = _strip_accents(value).lower()
    if "pere" in v:
        return "FATHER"
    if "mere" in v:
        return "MOTHER"
    return None


def _iso_date(value: str) -> str | None:
    return value if _ISO_DATE.match(value or "") else None


def build_declaration(
    report: dict, threshold: float = DEFAULT_THRESHOLD
) -> tuple[dict, list[str]]:
    """Map a scored report to (declaration, review_comment_lines).

    Returns only V2 birth field ids that exist in the POC form. Every
    format-valid value is prefilled — the registrar reviews the record against
    the scan anyway, so an unfilled probably-right value just costs typing.
    The threshold decides *flagging*, not filling: below it, the value is
    still sent but listed as "à vérifier" in the review comment. Only values
    OpenCRVS wants structured while we have free text (places, addresses)
    stay comment-only.
    """
    fields = report.get("fields", {})
    decl: dict = {}
    comments: list[str] = []

    def value_of(name: str) -> tuple[str | None, float]:
        f = fields.get(name) or {}
        v = f.get("value")
        return (str(v).strip() if v not in (None, "") else None), float(f.get("score", 0))

    def take(name: str) -> str | None:
        v, score = value_of(name)
        if v is None:
            return None
        if score < threshold:
            comments.append(f"à vérifier — {name} (confiance {score:.2f}): {v}")
        return v

    def comment_only(name: str, label: str) -> None:
        v, score = value_of(name)
        if v is not None:
            comments.append(f"{label} (OCR, confiance {score:.2f}): {v}")

    def take_first(names: tuple[str, ...]) -> str | None:
        for n in names:
            if v := take(n):
                return v
        return None

    def take_person_name(
        full_or_surname: tuple[str, ...],
        surname_only: tuple[str, ...],
        given: tuple[str, ...],
    ) -> dict | None:
        """Country packs name the same thing differently: one full-name field
        (enfant_nom), split surname/given fields (nom + prenoms), or both.
        A dedicated given-name field means the other field is the surname —
        only a lone full-name field needs the uppercase split heuristic."""
        first = take_first(given)
        family = take_first(surname_only) or take_first(full_or_surname)
        if family and first:
            return {"firstname": first, "surname": family}
        if family:
            return split_name(family)
        if first:
            return split_name(first)
        return None

    # ---- child ----
    if v := take_person_name(
        ("enfant_nom", "nom"),
        ("enfant_nom_famille", "nom_famille"),
        ("enfant_prenoms", "enfant_prenom", "prenoms", "prenom"),
    ):
        decl["child.name"] = v
    if (v := take("date_naissance")) and _iso_date(v):
        decl["child.dob"] = v
    if (v := take("sexe")) and map_gender(v):
        decl["child.gender"] = map_gender(v)
    # no structured mapping possible for free-text places/times -> comment
    comment_only("lieu_naissance", "Lieu de naissance")
    comment_only("heure_naissance", "Heure de naissance")

    # ---- father ----
    if v := take_person_name(
        ("pere_nom", "pere_nom_complet"),
        ("pere_nom_famille",),
        ("pere_prenoms", "pere_prenom"),
    ):
        decl["father.name"] = v
    if (v := take("pere_date_naissance")) and _iso_date(v):
        decl["father.dob"] = v
    if v := take("pere_nationalite"):
        if code := map_nationality(v):
            decl["father.nationality"] = code
        else:
            comments.append(f"Nationalité du père (OCR, non mappée): {v}")
    if v := take("pere_profession"):
        decl["father.occupation"] = v
    comment_only("pere_lieu_naissance", "Lieu de naissance du père")
    comment_only("pere_domicile", "Domicile du père")

    # ---- mother ----
    if v := take_person_name(
        ("mere_nom", "mere_nom_complet", "mere_nom_jeune_fille"),
        ("mere_nom_famille",),
        ("mere_prenoms", "mere_prenom"),
    ):
        decl["mother.name"] = v
    if (v := take("mere_date_naissance")) and _iso_date(v):
        decl["mother.dob"] = v
    if v := take("mere_nationalite"):
        if code := map_nationality(v):
            decl["mother.nationality"] = code
        else:
            comments.append(f"Nationalité de la mère (OCR, non mappée): {v}")
    if v := take("mere_profession"):
        decl["mother.occupation"] = v
    comment_only("mere_lieu_naissance", "Lieu de naissance de la mère")
    comment_only("mere_domicile", "Domicile de la mère")

    # ---- informant (declarant) ----
    for name in ("declarant_qualite", "declarant_lien", "declarant"):
        v, _ = value_of(name)
        if not v:
            continue
        if "informant.relation" not in decl and (rel := map_informant_relation(v)):
            decl["informant.relation"] = rel
        else:
            comment_only(name, name)

    # anything extracted but not handled above -> visible to the registrar
    handled = {
        "enfant_nom", "nom", "enfant_nom_famille", "nom_famille",
        "enfant_prenoms", "enfant_prenom", "prenoms", "prenom",
        "date_naissance", "sexe", "lieu_naissance", "heure_naissance",
        "pere_nom", "pere_nom_complet", "pere_nom_famille",
        "pere_prenoms", "pere_prenom",
        "pere_date_naissance", "pere_profession", "pere_lieu_naissance",
        "pere_domicile",
        "mere_nom", "mere_nom_complet", "mere_nom_jeune_fille",
        "mere_nom_famille", "mere_prenoms", "mere_prenom",
        "mere_date_naissance", "mere_profession", "mere_lieu_naissance",
        "mere_domicile", "declarant_qualite", "declarant_lien", "declarant",
        "pere_nationalite", "mere_nationalite",
    }
    for name in fields:
        if name not in handled:
            comment_only(name, name)

    return decl, comments


# ----------------------------------------------------------------------------
# place resolution (city -> admin hierarchy) via the VLM
# ----------------------------------------------------------------------------

# pack code -> (French country name for the prompt, ISO3 for the COUNTRY field)
_PACK_COUNTRIES = {
    "ao": ("Angola", "AGO"), "bj": ("Bénin", "BEN"), "cd": ("RD Congo", "COD"),
    "cg": ("Congo-Brazzaville", "COG"), "ci": ("Côte d'Ivoire", "CIV"),
    "cm": ("Cameroun", "CMR"), "cv": ("Cap-Vert", "CPV"),
    "dz": ("Algérie", "DZA"), "eg": ("Égypte", "EGY"), "ga": ("Gabon", "GAB"),
    "gn": ("Guinée", "GIN"), "ke": ("Kenya", "KEN"), "lb": ("Liban", "LBN"),
    "lr": ("Libéria", "LBR"), "ma": ("Maroc", "MAR"), "mg": ("Madagascar", "MDG"),
    "ml": ("Mali", "MLI"), "mr": ("Mauritanie", "MRT"), "mu": ("Maurice", "MUS"),
    "ng": ("Nigéria", "NGA"), "rw": ("Rwanda", "RWA"), "sc": ("Seychelles", "SYC"),
    "sl": ("Sierra Leone", "SLE"), "sn": ("Sénégal", "SEN"), "tg": ("Togo", "TGO"),
    "tn": ("Tunisie", "TUN"), "za": ("Afrique du Sud", "ZAF"),
}

# below this the VLM's place resolution is dropped (honesty gate: no
# confident-wrong prefill of administrative areas)
PLACE_CONFIDENCE_THRESHOLD = 0.7


def resolve_place(place: str, country_code: str, cache_dir: Path | None = None) -> dict | None:
    """Resolve a free-text birthplace to {state, district, postcode?}.

    Asks the VLM (same Gemini backend as extraction) for the administrative
    hierarchy of a known city. Returns None when the country pack is unknown,
    the model is unsure (confidence gate), or anything fails — the caller
    then simply leaves the place in the review comment, as before.
    """
    known = _PACK_COUNTRIES.get(country_code)
    if not known:
        return None
    country_name, iso3 = known

    cache_file = (cache_dir / "place_lookup.json") if cache_dir else None
    if cache_file and cache_file.exists():
        cached = json.loads(cache_file.read_text(encoding="utf-8"))
        if cached.get("place") == place:
            return cached.get("resolved")

    try:
        from .vlm_client import extract_json, make_client
        client = make_client("gemini")
        raw = client.chat(
            "Acte d'état civil — pays : " + country_name + ".\n"
            f"Le lieu de naissance lu par OCR est : « {place} ».\n"
            "Donne la hiérarchie administrative RÉELLE de ce lieu dans ce pays, "
            "en JSON strict :\n"
            '{"state": "<région/gouvernorat/province>", '
            '"district": "<département/délégation/district/ville>", '
            '"postcode": "<code postal, ou null si inconnu>", '
            '"confidence": <0.0-1.0>}\n'
            "confidence = ta certitude que ce lieu existe dans ce pays et que la "
            "hiérarchie est exacte. Lieu ambigu, illisible ou inconnu -> confidence "
            "basse. Réponds UNIQUEMENT le JSON.",
            thinking_budget=0,
        )
        out = extract_json(raw)
    except Exception:
        return None

    resolved = None
    if (
        isinstance(out, dict)
        and out.get("state") and out.get("district")
        and float(out.get("confidence", 0)) >= PLACE_CONFIDENCE_THRESHOLD
    ):
        resolved = {
            "country": iso3,
            "state": str(out["state"]),
            "district": str(out["district"]),
            "postcode": str(out["postcode"]) if out.get("postcode") else None,
            "confidence": float(out["confidence"]),
        }

    if cache_file:
        cache_file.write_text(
            json.dumps({"place": place, "resolved": resolved}, ensure_ascii=False, indent=1),
            encoding="utf-8",
        )
    return resolved


def enrich_birth_place(
    declaration: dict, comments: list[str], report: dict, run_dir: Path | None = None
) -> None:
    """Prefill child.placeOfBirth as an international address when the OCR
    birthplace resolves to a known city (state/district/zip via the VLM).

    Category is OTHER, never HEALTH_FACILITY/PRIVATE_HOME: the scan usually
    does not say where the delivery physically happened, and facilities would
    need instance UUIDs anyway.
    """
    if "child.placeOfBirth" in declaration:
        return
    place = ((report.get("fields", {}).get("lieu_naissance") or {}).get("value") or "").strip()
    country = (report.get("localization") or {}).get("country") or ""
    if not place:
        return
    resolved = resolve_place(place, country, cache_dir=run_dir)
    if not resolved:
        return

    details = {"state": resolved["state"], "district2": resolved["district"],
               "cityOrTown": place.title()}
    if resolved.get("postcode"):
        details["postcodeOrZip"] = resolved["postcode"]
    declaration["child.placeOfBirth"] = "OTHER"
    declaration["child.birthLocation.other"] = {
        "country": resolved["country"],
        "addressType": "INTERNATIONAL",
        "streetLevelDetails": details,
    }
    comments.append(
        f"Lieu de naissance résolu automatiquement (confiance {resolved['confidence']:.2f}): "
        f"{resolved['state']} / {resolved['district']}"
        + (f" / CP {resolved['postcode']}" if resolved.get("postcode") else "")
        + " — à confirmer"
    )


# ----------------------------------------------------------------------------
# API client
# ----------------------------------------------------------------------------


class OpenCRVSClient:
    def __init__(
        self,
        auth_url: str | None = None,
        gateway_url: str | None = None,
        client_id: str | None = None,
        client_secret: str | None = None,
    ):
        self.auth_url = (auth_url or os.environ.get("OPENCRVS_AUTH_URL", "")).rstrip("/")
        self.gateway_url = (gateway_url or os.environ.get("OPENCRVS_GATEWAY_URL", "")).rstrip("/")
        self.client_id = client_id or os.environ.get("OPENCRVS_CLIENT_ID", "")
        self.client_secret = client_secret or os.environ.get("OPENCRVS_CLIENT_SECRET", "")
        if not all((self.auth_url, self.gateway_url, self.client_id, self.client_secret)):
            raise ValueError(
                "OpenCRVS config missing: set OPENCRVS_AUTH_URL, OPENCRVS_GATEWAY_URL, "
                "OPENCRVS_CLIENT_ID, OPENCRVS_CLIENT_SECRET (see .env.example)"
            )
        self._token: str | None = None

    def token(self) -> str:
        if not self._token:
            out = _post(
                f"{self.auth_url}/token?client_id={self.client_id}"
                f"&client_secret={self.client_secret}&grant_type=client_credentials",
                {},
            )
            self._token = out["access_token"]
        return self._token

    def _auth_headers(self) -> dict:
        return {"Authorization": f"Bearer {self.token()}"}

    def create_event(self, event_type: str = "birth") -> str:
        out = _post(
            f"{self.gateway_url}/events/events",
            {"type": event_type, "transactionId": str(uuid.uuid4())},
            headers=self._auth_headers(),
        )
        return out["id"]

    def upload_file(self, event_id: str, file_path: str | Path) -> dict:
        """Upload a scan to MinIO via the gateway and return a FILE field value.

        POST {gateway}/upload (multipart: file, transactionId, path=eventId)
        stores the file as /<bucket>/<eventId>/<transactionId>.<ext> and
        returns that path; the dict slots into any documents.* FILE field.
        """
        import urllib.request

        p = Path(file_path)
        mime = {
            ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
            ".pdf": "application/pdf", ".tif": "image/tiff",
            ".tiff": "image/tiff", ".webp": "image/webp",
        }.get(p.suffix.lower(), "application/octet-stream")

        boundary = uuid.uuid4().hex
        parts = []
        for name, value in (("transactionId", str(uuid.uuid4())), ("path", event_id)):
            parts.append(
                f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"'
                f"\r\n\r\n{value}\r\n".encode()
            )
        parts.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="file"; '
            f'filename="{p.name}"\r\nContent-Type: {mime}\r\n\r\n'.encode()
            + p.read_bytes() + b"\r\n"
        )
        parts.append(f"--{boundary}--\r\n".encode())
        body = b"".join(parts)

        req = urllib.request.Request(
            f"{self.gateway_url}/upload",
            data=body,
            headers={
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                **self._auth_headers(),
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=120) as r:
            raw = r.read().decode().strip()
        # the handler returns the FullDocumentPath as a bare (JSON) string
        path = json.loads(raw) if raw.startswith('"') else raw
        return {"path": path, "originalFilename": p.name, "type": mime}

    def notify(
        self,
        event_id: str,
        declaration: dict,
        created_at_location: str | None = None,
        comment: str | None = None,
    ) -> dict:
        payload: dict = {
            "eventId": event_id,
            "transactionId": str(uuid.uuid4()),
            "declaration": declaration,
        }
        location = created_at_location or os.environ.get("OPENCRVS_LOCATION_ID")
        if location:
            payload["createdAtLocation"] = location
        if comment:
            payload["annotation"] = {"review.comment": comment}
        return _post(
            f"{self.gateway_url}/events/events/notifications",
            payload,
            headers=self._auth_headers(),
        )


def send_report(
    report_path: str | Path,
    threshold: float = DEFAULT_THRESHOLD,
    dry_run: bool = False,
) -> dict:
    """Full flow for one processed document: report.json -> notification.

    Returns {"declaration", "comment", "event_id" (unless dry_run)}.
    """
    report = json.loads(Path(report_path).read_text(encoding="utf-8"))
    declaration, comments = build_declaration(report, threshold)
    run_dir = Path(report_path).parent
    enrich_birth_place(declaration, comments, report, run_dir=run_dir)
    doc_id = report.get("doc_id", run_dir.name)
    header = f"Prérempli par OCR (document {doc_id})."
    comment = "\n".join([header] + comments)

    # attach the raw scan as proof of birth when the run kept it
    # (run_pipeline copies the input to original.<ext>)
    original = next(
        (p for p in run_dir.glob("original.*")
         if p.suffix.lower() in (".jpg", ".jpeg", ".png", ".pdf", ".tif", ".tiff", ".webp")),
        None,
    )

    result = {"declaration": declaration, "comment": comment}
    if dry_run:
        if original:
            result["attachment"] = original.name
        return result

    client = OpenCRVSClient()
    event_id = client.create_event("birth")
    if original:
        declaration["documents.proofOfBirth"] = client.upload_file(event_id, original)
    client.notify(event_id, declaration, comment=comment)
    result["event_id"] = event_id
    return result

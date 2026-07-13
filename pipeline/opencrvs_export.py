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
        return {"firstname": "", "surname": tokens[0]}
    return {"firstname": " ".join(tokens[:-1]), "surname": tokens[-1]}


def map_gender(value: str) -> str | None:
    v = _strip_accents(value).strip().lower()
    if v in ("masculin", "m", "male", "garcon"):
        return "male"
    if v in ("feminin", "f", "female", "fille"):
        return "female"
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

    # ---- child ----
    if v := take("enfant_nom"):
        decl["child.name"] = split_name(v)
    if (v := take("date_naissance")) and _iso_date(v):
        decl["child.dob"] = v
    if (v := take("sexe")) and map_gender(v):
        decl["child.gender"] = map_gender(v)
    # no structured mapping possible for free-text places/times -> comment
    comment_only("lieu_naissance", "Lieu de naissance")
    comment_only("heure_naissance", "Heure de naissance")

    # ---- father ----
    if v := take("pere_nom"):
        decl["father.name"] = split_name(v)
    if (v := take("pere_date_naissance")) and _iso_date(v):
        decl["father.dob"] = v
    if v := take("pere_profession"):
        decl["father.occupation"] = v
    comment_only("pere_lieu_naissance", "Lieu de naissance du père")
    comment_only("pere_domicile", "Domicile du père")

    # ---- mother ----
    if v := take("mere_nom"):
        decl["mother.name"] = split_name(v)
    if (v := take("mere_date_naissance")) and _iso_date(v):
        decl["mother.dob"] = v
    if v := take("mere_profession"):
        decl["mother.occupation"] = v
    comment_only("mere_lieu_naissance", "Lieu de naissance de la mère")
    comment_only("mere_domicile", "Domicile de la mère")

    # ---- informant (declarant) ----
    for name in ("declarant_qualite", "declarant"):
        v, _ = value_of(name)
        if v and (rel := map_informant_relation(v)):
            decl["informant.relation"] = rel
            break

    # anything extracted but not handled above -> visible to the registrar
    handled = {
        "enfant_nom", "date_naissance", "sexe", "lieu_naissance", "heure_naissance",
        "pere_nom", "pere_date_naissance", "pere_profession", "pere_lieu_naissance",
        "pere_domicile", "mere_nom", "mere_date_naissance", "mere_profession",
        "mere_lieu_naissance", "mere_domicile", "declarant_qualite", "declarant",
    }
    for name in fields:
        if name not in handled:
            comment_only(name, name)

    return decl, comments


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
    doc_id = report.get("doc_id", Path(report_path).parent.name)
    header = f"Prérempli par OCR (document {doc_id})."
    comment = "\n".join([header] + comments)

    result = {"declaration": declaration, "comment": comment}
    if dry_run:
        return result

    client = OpenCRVSClient()
    event_id = client.create_event("birth")
    client.notify(event_id, declaration, comment=comment)
    result["event_id"] = event_id
    return result

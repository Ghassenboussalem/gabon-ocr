"""Stage 4 — Validation: turn "the model said X" into "X is consistent".

Civil-status documents are unusually rich in redundancy, and we exploit all
of it:

  * dates are often written TWICE (in digits after "Du", in words after "Le") —
    they must agree
  * the C.N.I. line frequently embeds the holder's birth date
    ("476 du 15.03.1971") — it must match the declared Date de Naissance
  * chronology must hold (birth <= registration; parents plausibly older)
  * places should exist (fuzzy-matched against a Gabon gazetteer)
  * enums are closed (sexe)

Every check yields a Finding(level ok|warn|fail). Findings feed the
confidence score and are displayed verbatim to the human reviewer, so the
reviewer sees "CNIN date 17.10.1984 != declared 16.10.1984" instead of a
bare low-confidence flag.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import date

from rapidfuzz import fuzz, process

# ----------------------------------------------------------------------------
# French date-in-words parser ("vingt trois janvier deux mil deux")
# ----------------------------------------------------------------------------

MONTHS = {
    "janvier": 1, "fevrier": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6,
    "juillet": 7, "aout": 8, "septembre": 9, "octobre": 10, "novembre": 11,
    "decembre": 12,
}

_UNITS = {
    "zero": 0, "un": 1, "une": 1, "premier": 1, "deux": 2, "trois": 3,
    "quatre": 4, "cinq": 5, "six": 6, "sept": 7, "huit": 8, "neuf": 9,
    "dix": 10, "onze": 11, "douze": 12, "treize": 13, "quatorze": 14,
    "quinze": 15, "seize": 16, "vingt": 20, "trente": 30, "quarante": 40,
    "cinquante": 50, "soixante": 60,
}
_STOP = {"l", "l'an", "an", "le", "la", "du", "de", "et", "en", "annee", "jour", "mil?"}


def _ascii(s: str) -> str:
    s = unicodedata.normalize("NFKD", s)
    return "".join(c for c in s if not unicodedata.combining(c)).lower()


def _pretokenize(s: str) -> list[str]:
    s = _ascii(s).replace("-", " ").replace("'", " ")
    # collapse compound tens BEFORE parsing so "quatre vingt onze" is unambiguous
    s = re.sub(r"\bquatre\s+vingts?\s+dix\b", " __90 ", s)
    s = re.sub(r"\bquatre\s+vingts?\b", " __80 ", s)
    s = re.sub(r"\bsoixante\s+dix\b", " __70 ", s)
    toks = [t for t in s.split() if t and t not in _STOP]
    return toks


def _words_to_int(tokens: list[str]) -> int | None:
    total, cur, seen = 0, 0, False
    for t in tokens:
        if t.startswith("__"):
            cur += int(t[2:]); seen = True
        elif t in ("mil", "mille"):
            total += (cur or 1) * 1000; cur = 0; seen = True
        elif t in ("cent", "cents"):
            cur = (cur or 1) * 100; seen = True
        elif t in _UNITS:
            cur += _UNITS[t]; seen = True
        elif t.isdigit():
            cur += int(t); seen = True
        else:
            return None  # unknown word inside a number -> refuse to guess
    return total + cur if seen else None


def parse_french_date_words(s: str) -> date | None:
    toks = _pretokenize(s)
    if not toks:
        return None
    # find the month (fuzzy: handwriting transcriptions carry small errors)
    m_idx, m_val, best = None, None, 0
    for i, t in enumerate(toks):
        match = process.extractOne(t, MONTHS.keys(), scorer=fuzz.ratio)
        if match and match[1] >= 84 and match[1] > best:
            m_idx, m_val, best = i, MONTHS[match[0]], match[1]
    if m_idx is None:
        return None
    day = _words_to_int(toks[:m_idx])
    year = _words_to_int(toks[m_idx + 1 :])
    if not day or not year:
        return None
    if year < 100:  # "quatre vingt onze" alone -> 1991-style shorthand
        year += 1900
    try:
        return date(year, m_val, day)
    except ValueError:
        return None


_NUM_DATE = re.compile(r"(\d{1,2})\s*[./\-\s]\s*(\d{1,2})\s*[./\-\s]\s*(\d{2,4})")


def parse_date_any(s: str | None) -> date | None:
    """ISO, numeric dd.mm.yyyy variants, or French words."""
    if not s:
        return None
    s = str(s).strip()
    m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        try:
            return date(int(m[1]), int(m[2]), int(m[3]))
        except ValueError:
            return None
    m = _NUM_DATE.search(s)
    if m:
        d, mo, y = int(m[1]), int(m[2]), int(m[3])
        if y < 100:
            y += 1900 if y > 30 else 2000
        try:
            return date(y, mo, d)
        except ValueError:
            return None
    return parse_french_date_words(s)


def dates_in_text(s: str | None) -> list[date]:
    if not s:
        return []
    out = []
    for m in _NUM_DATE.finditer(str(s)):
        d = parse_date_any(m.group(0))
        if d:
            out.append(d)
    return out


# ----------------------------------------------------------------------------
# Gazetteer
# ----------------------------------------------------------------------------

GABON_PLACES = [
    # provinces
    "Estuaire", "Haut-Ogooué", "Moyen-Ogooué", "Ngounié", "Nyanga",
    "Ogooué-Ivindo", "Ogooué-Lolo", "Ogooué-Maritime", "Woleu-Ntem",
    # communes / towns
    "Libreville", "Port-Gentil", "Franceville", "Oyem", "Moanda", "Mouila",
    "Lambaréné", "Tchibanga", "Koulamoutou", "Makokou", "Bitam", "Gamba",
    "Mounana", "Ndendé", "Ntoum", "Owendo", "Akanda", "Mitzic", "Ndjolé",
    "Booué", "Fougamou", "Mayumba", "Lastoursville", "Okondja", "Minvoul",
    "Médouneu", "Cocobeach", "Mékambo", "Omboué", "Léconi",
    # frequent Libreville districts on these forms
    "Nzeng-Ayong", "Akébé", "Nkembo", "Lalala", "PK8", "Glass", "Oloumi",
    # frequent foreign entries (parents born abroad)
    "Cameroun", "Foumban", "Douala", "Yaoundé", "Bafoussam",
    "Congo", "Brazzaville", "Pointe-Noire", "Guinée Équatoriale", "Bata",
    "Bénin", "Togo", "Lomé", "Cotonou", "Mali", "Bamako", "Sénégal", "Dakar",
    "Nigéria", "Lagos",
]
_PLACE_KEYS = {_ascii(p): p for p in GABON_PLACES}


def canonical_place(s: str | None, places: list[str] | None = None) -> tuple[str | None, float]:
    """Fuzzy-canonicalize a place against a gazetteer (default: Gabon).
    Country packs supply their own list. Returns (canonical or original, score)."""
    if not s:
        return None, 0.0
    keys = {_ascii(p): p for p in places} if places else _PLACE_KEYS
    q = _ascii(str(s))
    match = process.extractOne(q, keys.keys(), scorer=fuzz.WRatio)
    if match and match[1] >= 88:
        return keys[match[0]], match[1] / 100
    return str(s), (match[1] / 100 if match else 0.0)


# ----------------------------------------------------------------------------
# Cross-field checks
# ----------------------------------------------------------------------------


@dataclass
class Finding:
    field: str
    level: str  # ok | warn | fail
    message: str

    def as_dict(self):
        return {"field": self.field, "level": self.level, "message": self.message}


def _get(rec: dict, name: str):
    e = rec.get(name) or {}
    return e.get("value"), e.get("raw", "")


def run_checks(record: dict, places: list[str] | None = None,
               checks: dict | None = None) -> list[Finding]:
    checks = checks or {}
    F: list[Finding] = []

    # --- enums ---
    sexe, _ = _get(record, "sexe")
    if sexe and _ascii(str(sexe)) not in ("masculin", "feminin"):
        F.append(Finding("sexe", "fail", f"sexe {sexe!r} n'est pas Masculin/Féminin"))
    elif sexe:
        F.append(Finding("sexe", "ok", "sexe valide"))

    # --- dates parse + words/digits agreement ---
    parsed: dict[str, date | None] = {}
    for name in ("date_enregistrement", "date_naissance", "date_declaration",
                 "date_etablissement", "date_acte",
                 "date_delivrance", "pere_date_naissance", "mere_date_naissance"):
        val, raw = _get(record, name)
        d = parse_date_any(val) or parse_date_any(raw)
        parsed[name] = d
        if val and not d:
            F.append(Finding(name, "warn", f"date non interprétable: {val!r}"))
        if d and raw:
            d_words = parse_french_date_words(str(raw))
            d_digits = next(iter(dates_in_text(str(raw))), None)
            if d_words and d_digits and d_words != d_digits:
                F.append(Finding(name, "warn",
                         f"date en lettres {d_words} ≠ date en chiffres {d_digits} dans le même champ"))
            elif d_words and d_digits:
                F.append(Finding(name, "ok", "date en lettres et en chiffres concordent"))

    # --- chronology ---
    dn = parsed.get("date_naissance")
    de, de_field = None, "date_enregistrement"
    for _f in ("date_enregistrement", "date_declaration", "date_etablissement", "date_acte"):
        if parsed.get(_f):
            de, de_field = parsed[_f], _f
            break
    if dn and de:
        if dn > de:
            F.append(Finding("date_naissance", "fail",
                     f"naissance {dn} postérieure à l'enregistrement {de}"))
        elif (de - dn).days > 365 * 5:
            F.append(Finding(de_field, "warn",
                     f"enregistrement {(de - dn).days} jours après la naissance (jugement supplétif ?)"))
        else:
            F.append(Finding("date_naissance", "ok", "chronologie naissance/enregistrement cohérente"))
    for parent in ("pere", "mere"):
        dp = parsed.get(f"{parent}_date_naissance")
        if dp and dn:
            age = (dn - dp).days / 365.25
            if age < 12:
                F.append(Finding(f"{parent}_date_naissance", "warn",
                         f"{parent} aurait {age:.0f} ans à la naissance de l'enfant"))

    # --- CNIN embedded date vs declared birth date (country-gated) ---
    for parent in ("pere", "mere") if checks.get("cnin_date", True) else ():
        _, cnin_raw = _get(record, f"{parent}_cnin")
        cnin_val, _r = _get(record, f"{parent}_cnin")
        text = " ".join(str(x) for x in (cnin_val, cnin_raw) if x)
        embedded = dates_in_text(text)
        declared = parsed.get(f"{parent}_date_naissance")
        if embedded and declared:
            if any(d == declared for d in embedded):
                F.append(Finding(f"{parent}_cnin", "ok",
                         "date incluse dans la C.N.I. concorde avec la date de naissance"))
            else:
                F.append(Finding(f"{parent}_cnin", "warn",
                         f"date dans la C.N.I. {embedded[0].strftime('%d.%m.%Y')} ≠ "
                         f"date de naissance déclarée {declared.strftime('%d.%m.%Y')} — vérifier"))

    # --- reference numbers embedding a year must match the act's year ---
    if checks.get("reference_year"):
        d_ref = (parsed.get("date_enregistrement") or parsed.get("date_declaration")
                 or parsed.get("date_etablissement") or parsed.get("date_acte"))
        if d_ref:
            for name in ("annee", "annee_registre", "reference", "acte_numero",
                         "registre", "numero_acte"):
                val, raw = _get(record, name)
                text = " ".join(str(x) for x in (val, raw) if x)
                m = re.search(r"\b(19|20)\d{2}\b", text)
                if not m:
                    continue
                if int(m.group(0)) == d_ref.year:
                    F.append(Finding(name, "ok",
                             "l'année de la référence concorde avec l'acte"))
                else:
                    F.append(Finding(name, "warn",
                             f"année dans la référence {m.group(0)} ≠ année de l'acte {d_ref.year}"))

    # --- cross-section field equality (e.g. Mauritanie: le prénom du père
    #     dans la section Enfant doit égaler Prénom dans la section Père) ---
    for f1, f2 in checks.get("equal_pairs", []):
        v1, r1 = _get(record, f1)
        v2, r2 = _get(record, f2)
        a, b = str(v1 or r1 or ""), str(v2 or r2 or "")
        if a and b:
            if fuzz.ratio(_ascii(a), _ascii(b)) >= 90:
                F.append(Finding(f1, "ok", f"concorde avec {f2}"))
            else:
                F.append(Finding(f1, "warn", f"{a!r} ≠ {f2} = {b!r} — vérifier"))

    # --- national ID number embeds the birth date (Maurice, Afrique du Sud) ---
    fmt = checks.get("id_birthdate_format")
    if fmt in ("ddmmyy", "yymmdd", "cyymmdd") and parsed.get("date_naissance"):
        dn_ = parsed["date_naissance"]
        for name in ("nid_numero", "numero_identite", "enfant_nid"):
            val, raw = _get(record, name)
            text = str(val or raw or "")
            runs = re.findall(r"\d{6,}", re.sub(r"[\s./-]", "", text))
            if not runs:
                continue
            six = runs[0][1:7] if fmt == "cyymmdd" else runs[0][:6]
            try:
                if fmt == "ddmmyy":
                    d_, m_, y_ = int(six[0:2]), int(six[2:4]), int(six[4:6])
                else:
                    y_, m_, d_ = int(six[0:2]), int(six[2:4]), int(six[4:6])
                century = 1900 if (dn_.year % 100) == y_ and dn_.year < 2000 else 2000
                from datetime import date as _date
                embedded = _date(century + y_, m_, d_)
            except ValueError:
                F.append(Finding(name, "warn",
                         f"les 6 premiers chiffres de l'identifiant ({six}) ne forment pas une date"))
                continue
            if embedded == dn_:
                F.append(Finding(name, "ok",
                         "la date incluse dans le n° d'identité concorde avec la date de naissance"))
            else:
                F.append(Finding(name, "warn",
                         f"date dans le n° d'identité {embedded} ≠ date de naissance {dn_}"))
            break

    # --- margin date must equal the declared birth date (e.g. Algeria) ---
    if checks.get("margin_date_matches_birth"):
        dm_val, dm_raw = _get(record, "date_marge")
        dm = parse_date_any(dm_val) or parse_date_any(dm_raw)
        if dm and parsed.get("date_naissance"):
            if dm == parsed["date_naissance"]:
                F.append(Finding("date_marge", "ok",
                         "date en marge concorde avec la date de naissance"))
            else:
                F.append(Finding("date_marge", "warn",
                         f"date en marge {dm} ≠ date de naissance {parsed['date_naissance']}"))

    # --- numbers written in words vs digits (Angola, Sénégal, ...) ---
    if checks.get("acte_number_words"):
        pairs = checks.get("number_word_pairs",
                           [["numero_acte_lettres", "numero_acte_marge"]])
        for w_field, d_field in pairs:
            w_val, w_raw = _get(record, w_field)
            d_val, d_raw = _get(record, d_field)
            w_text = re.sub(r"(?i)\b(n|no|n°|an|numero|numéro|acte)\b|[°:()]", " ",
                            str(w_val or w_raw or ""))
            words = _words_to_int(_pretokenize(w_text))
            m = re.search(r"\d[\d.\s]*", str(d_val or d_raw or ""))
            digits = int(re.sub(r"[^\d]", "", m.group(0))) if m else None
            if words and digits:
                if words == digits:
                    F.append(Finding(w_field, "ok",
                             f"valeur en toutes lettres concorde avec les chiffres ({digits})"))
                else:
                    F.append(Finding(w_field, "warn",
                             f"en lettres = {words} ≠ en chiffres = {digits} ({d_field})"))

    # --- registry year vs declaration date (country-gated) ---
    if checks.get("annee_matches_declaration"):
        annee, _ = _get(record, "annee")
        d_ref = parsed.get("date_declaration") or parse_date_any(_get(record, "date_declaration")[0])
        if annee and d_ref:
            try:
                if int(str(annee).strip()) != d_ref.year:
                    F.append(Finding("annee", "warn",
                             f"année du registre {annee} ≠ année de la déclaration {d_ref.year}"))
                else:
                    F.append(Finding("annee", "ok", "année du registre concorde avec la déclaration"))
            except ValueError:
                F.append(Finding("annee", "warn", f"année du registre non numérique: {annee!r}"))

    # --- places ---
    for name in ("lieu_naissance", "pere_lieu_naissance", "pere_domicile",
                 "mere_lieu_naissance", "mere_domicile",
                 "gouvernorat", "delegation", "commune", "lieu_delivrance"):
        val, _ = _get(record, name)
        if not val:
            continue
        canon, score = canonical_place(val, places)
        if score >= 0.88:
            if _ascii(canon) != _ascii(str(val)):
                F.append(Finding(name, "ok", f"lieu reconnu: {val!r} → {canon!r}"))
                record[name]["value"] = canon
            else:
                F.append(Finding(name, "ok", "lieu reconnu"))
        else:
            F.append(Finding(name, "warn", f"lieu non reconnu dans le gazetier: {val!r}"))

    # --- required fields present ---
    name_field = next((n for n in ("enfant_nom", "nom", "enfant_prenom",
                                   "enfant_prenoms", "nom_famille") if n in record),
                      "enfant_nom")
    for name in (name_field, "date_naissance", "sexe"):
        val, _ = _get(record, name)
        if not val:
            F.append(Finding(name, "warn", "champ essentiel vide ou illisible"))

    return F

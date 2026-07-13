"""Offline tests for the OCR -> OpenCRVS notification mapper."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.opencrvs_export import (
    build_declaration,
    map_gender,
    map_informant_relation,
    split_name,
)


def _field(value, score):
    return {"value": value, "score": score}


REPORT = {
    "doc_id": "test_doc",
    "fields": {
        "enfant_nom": _field("Yamousso THIAM", 0.9),
        "date_naissance": _field("1959-07-23", 0.95),
        "sexe": _field("Féminin", 0.9),
        "heure_naissance": _field("17:00", 0.8),
        "lieu_naissance": _field("Clinique du Belvédère à Abidjan", 0.85),
        "pere_nom": _field("Amadou THIAM", 0.88),
        "pere_date_naissance": _field("1923-08-05", 0.9),
        "pere_profession": _field("Directeur de la Radiodiffusion", 0.75),
        "mere_nom": _field("Marietou SOW", 0.87),
        "mere_date_naissance": _field("le quinze Decembre", 0.7),   # not ISO
        "mere_profession": _field("sans profession", 0.4),          # low confidence
        "declarant_qualite": _field("du père", 0.8),
        "officier": _field("Jean PORQUET", 0.9),                    # unmapped
    },
}


def test_split_name():
    assert split_name("Yamousso THIAM") == {"firstname": "Yamousso", "surname": "THIAM"}
    assert split_name("Mamadou Dadel COULIBALY") == {
        "firstname": "Mamadou Dadel", "surname": "COULIBALY"}
    assert split_name("BOLE MIRIAM Titi") == {
        "firstname": "Titi", "surname": "BOLE MIRIAM"}
    assert split_name("Jean Dupont") == {"firstname": "Jean", "surname": "Dupont"}
    assert split_name("THIAM") == {"firstname": "", "surname": "THIAM"}
    assert split_name("") == {"firstname": "", "surname": ""}


def test_enum_mappings():
    assert map_gender("Féminin") == "female"
    assert map_gender("MASCULIN") == "male"
    assert map_gender("indéterminé") is None
    assert map_informant_relation("du père") == "FATHER"
    assert map_informant_relation("la mère de l'enfant") == "MOTHER"
    assert map_informant_relation("le grand-oncle") is None


def test_build_declaration():
    decl, comments = build_declaration(REPORT, threshold=0.6)

    assert decl["child.name"] == {"firstname": "Yamousso", "surname": "THIAM"}
    assert decl["child.dob"] == "1959-07-23"
    assert decl["child.gender"] == "female"
    assert decl["father.name"] == {"firstname": "Amadou", "surname": "THIAM"}
    assert decl["father.dob"] == "1923-08-05"
    assert decl["father.occupation"] == "Directeur de la Radiodiffusion"
    assert decl["mother.name"] == {"firstname": "Marietou", "surname": "SOW"}
    assert decl["informant.relation"] == "FATHER"

    # non-ISO date must NOT be prefilled (format gate is absolute)
    assert "mother.dob" not in decl
    # low-confidence value IS prefilled...
    assert decl["mother.occupation"] == "sans profession"
    # ...but flagged for the registrar
    assert any("à vérifier" in c and "sans profession" in c for c in comments)
    # free-text place has no structured field
    assert not any(k.startswith("child.placeOfBirth") for k in decl)

    joined = "\n".join(comments)
    # everything unmapped is surfaced to the registrar
    assert "Clinique du Belvédère" in joined
    assert "Jean PORQUET" in joined
    assert "17:00" in joined

    # only known V2 field ids are emitted
    allowed_prefixes = ("child.", "mother.", "father.", "informant.")
    assert all(k.startswith(allowed_prefixes) for k in decl)


def test_empty_report():
    decl, comments = build_declaration({"fields": {}})
    assert decl == {} and comments == []


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"{name}: OK")
    print("ALL TESTS PASSED")

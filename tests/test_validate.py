from datetime import date

from pipeline.validate import (
    canonical_place,
    dates_in_text,
    parse_date_any,
    parse_french_date_words,
)


def test_date_words():
    assert parse_french_date_words("vingt deux avril mil neuf cent quatre vingt onze") == date(1991, 4, 22)
    assert parse_french_date_words("Quatre Février deux mil deux") == date(2002, 2, 4)
    assert parse_french_date_words("treize juin l'an deux mil trois") == date(2003, 6, 13)
    assert parse_french_date_words("huit avril mil neuf cent quatre-vingt-onze") == date(1991, 4, 8)
    assert parse_french_date_words("premier janvier deux mille vingt") == date(2020, 1, 1)
    assert parse_french_date_words("dix sept octobre mil neuf cent quatre vingt quatre") == date(1984, 10, 17)
    # refuses to guess on garbage
    assert parse_french_date_words("bonjour le monde") is None


def test_date_numeric():
    assert parse_date_any("15.03.1971") == date(1971, 3, 15)
    assert parse_date_any("16-10-1984") == date(1984, 10, 16)
    assert parse_date_any("04/02/2002") == date(2002, 2, 4)
    assert parse_date_any("2002-01-23") == date(2002, 1, 23)
    assert parse_date_any("Vingt trois Janvier deux mil deux") == date(2002, 1, 23)
    assert parse_date_any(None) is None


def test_dates_in_text():
    assert dates_in_text("A.N° 476 du 15.03.1971") == [date(1971, 3, 15)]
    assert dates_in_text("8172 du 17.10.1984") == [date(1984, 10, 17)]
    assert dates_in_text("rien ici") == []


def test_gazetteer():
    assert canonical_place("Libreville")[0] == "Libreville"
    assert canonical_place("LIBREVILE")[0] == "Libreville"   # handwriting typo
    assert canonical_place("Nzeng Ayong")[0] == "Nzeng-Ayong"
    assert canonical_place("Foumban")[0] == "Foumban"


if __name__ == "__main__":
    test_date_words()
    test_date_numeric()
    test_dates_in_text()
    test_gazetteer()
    print("all validate tests passed")

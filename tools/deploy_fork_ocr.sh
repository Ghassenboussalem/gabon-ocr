#!/bin/bash
# Deploy the OCR prefill module into the countryconfig fork checked out in
# the ubuntu-opencrvs WSL distro, and wire every field the OCR can fill.
#
#   wsl -d ubuntu-opencrvs -u root -- bash /mnt/c/Users/Ghassen/Documents/gabon-ocr/tools/deploy_fork_ocr.sh
#
# Idempotent: re-running refreshes ocr.ts and skips files already wired.
set -eu

FORK=/opt/opencrvs/opencrvs-countryconfig
SRC=/mnt/c/Users/Ghassen/Documents/gabon-ocr/fork
PAGES=$FORK/src/form/v2/birth/forms/pages

tr -d '\r' < "$SRC/ocr.ts" > "$FORK/src/form/v2/ocr.ts"
echo "copied  src/form/v2/ocr.ts"

python3 - "$FORK" "$PAGES" <<'PYEOF'
import io, sys

FORK, PAGES = sys.argv[1], sys.argv[2]

IMPORT = (
    "import {\n"
    "  getOcrPrefillFields,\n"
    "  ocrParent,\n"
    "  ocrValue\n"
    "} from '@countryconfig/form/v2/ocr'"
)

def read(p):
    return io.open(p, encoding="utf-8").read()

def write(p, s):
    io.open(p, "w", encoding="utf-8").write(s)

def add_import(src, anchor, what=IMPORT):
    if what.split("\n")[-1] in src:
        return src
    assert anchor in src, "import anchor missing"
    return src.replace(anchor, anchor + "\n" + what, 1)

def wire_plain(src, field_id, indent="      "):
    """Plain field: inject parent + value right after its `id:` line.

    Both are required — the client's listener map is built from `parent`,
    and `value` is only re-resolved when a declared parent changes.
    """
    needle = "%sid: '%s',\n" % (indent, field_id)
    if needle not in src:
        print("   WARN  %s not found" % field_id)
        return src
    add = ("%sparent: ocrParent(),\n%svalue: ocrValue('%s'),\n"
           % (indent, indent, field_id))
    return src.replace(needle, needle + add, 1)

# ---------------------------------------------------------------- child ----
p = PAGES + "/child.ts"
src = read(p)
if "ocrParent" in src:
    print("SKIP    child.ts (already wired)")
else:
    # a first pass wired `value` only; upgrade it in place
    src = src.replace(
        "import {\n  getOcrPrefillFields,\n  ocrValue\n} from '@countryconfig/form/v2/ocr'",
        IMPORT, 1)
    src = add_import(
        src,
        "import { applicationConfig } from '@countryconfig/api/application/application-config'")
    for fid in ["child.name", "child.gender", "child.dob",
                "child.placeOfBirth", "child.birthLocation.other"]:
        old = "      value: ocrValue('%s'),\n" % fid
        if old in src:
            src = src.replace(old, "      parent: ocrParent(),\n" + old, 1)
        else:
            src = wire_plain(src, fid)
    if "getOcrPrefillFields()" not in src:
        tail = "\n  ]\n})"
        idx = src.rstrip().rfind(tail)
        assert idx != -1
        src = src[:idx] + ",\n    ...getOcrPrefillFields()" + src[idx:]
    write(p, src)
    print("PATCHED child.ts")

# ------------------------------------------- mother / father / informant ----
PLAIN = {
    "mother.ts": ["mother.nationality", "mother.occupation"],
    "father.ts": ["father.nationality", "father.occupation"],
    "informant.ts": ["informant.relation"],
}
for fname, fields in PLAIN.items():
    p = PAGES + "/" + fname
    src = read(p)
    if "ocrValue" in src:
        print("SKIP    %s (already wired)" % fname)
        continue
    # anchor on the toolkit import, the one line every page is guaranteed
    # to have regardless of which helpers it pulls in
    src = add_import(
        src,
        "} from '@opencrvs/toolkit/events'",
        what="import { ocrParent, ocrValue } from '@countryconfig/form/v2/ocr'")
    for fid in fields:
        src = wire_plain(src, fid)
    write(p, src)
    print("PATCHED %s" % fname)

# ------------------------------------------------------------ documents ----
# le reperage OCR (image des zones lues) est joint parmi les pieces
# justificatives : le registraire voit d ou vient chaque valeur, pas
# seulement ce qu elle dit
p = PAGES + "/documents.ts"
src = read(p)
if "getOcrDocumentFields" in src:
    print("SKIP    documents.ts (already wired)")
else:
    src = add_import(
        src,
        "} from '@opencrvs/toolkit/events'",
        what="import { getOcrDocumentFields } from '@countryconfig/form/v2/ocr'")
    tail = "\n  ]\n})"
    idx = src.rstrip().rfind(tail)
    assert idx != -1, "unexpected end of documents.ts"
    src = src[:idx] + ",\n    ...getOcrDocumentFields()" + src[idx:]
    write(p, src)
    print("PATCHED documents.ts")

# ---------------------------------------------------------------- mosip ----
# mother.name / mother.dob and their father / informant twins are wrapped in
# connectToMOSIPIdReader, which rebuilds `parent` and overwrites `value`, so
# injecting into the wrapped object is futile. Teach the wrapper to carry the
# OCR references too: MOSIP keeps priority, OCR fills in when MOSIP is silent.
p = FORK + "/src/form/v2/mosip.ts"
src = read(p)
if "ocrValue" in src:
    print("SKIP    mosip.ts (already wired)")
else:
    src = add_import(
        src,
        "import { addYears, isAfter } from 'date-fns'",
        what="import { ocrParent, ocrValue } from '@countryconfig/form/v2/ocr'")
    old = """      parent: [
        field(`${page}.id-reader`),
        field(`${page}.verify-nid-http-fetch`),
        ...(parent ? [parent] : [])
      ],
      ...fieldInput,
      value: [
        field(`${page}.verify-nid-http-fetch`).get(valuePath),
        field(`${page}.id-reader`).get(valuePath)
      ]"""
    new = """      parent: [
        field(`${page}.id-reader`),
        field(`${page}.verify-nid-http-fetch`),
        ...ocrParent(),
        ...(parent ? [parent] : [])
      ],
      ...fieldInput,
      value: [
        field(`${page}.verify-nid-http-fetch`).get(valuePath),
        field(`${page}.id-reader`).get(valuePath),
        ...ocrValue(fieldInput.id)
      ]"""
    assert old in src, "connectToMOSIPIdReader shape changed"
    src = src.replace(old, new, 1)
    write(p, src)
    print("PATCHED mosip.ts")
PYEOF

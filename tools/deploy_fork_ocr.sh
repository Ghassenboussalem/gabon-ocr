#!/bin/bash
# Deploy the OCR prefill module into the countryconfig fork checked out in
# the ubuntu-opencrvs WSL distro, and wire it into the birth child page.
#
#   wsl -d ubuntu-opencrvs -u root -- bash /mnt/c/Users/Ghassen/Documents/gabon-ocr/tools/deploy_fork_ocr.sh
#
# Idempotent: re-running only refreshes ocr.ts if child.ts is already wired.
set -eu

FORK=/opt/opencrvs/opencrvs-countryconfig
SRC=/mnt/c/Users/Ghassen/Documents/gabon-ocr/fork
CHILD=$FORK/src/form/v2/birth/forms/pages/child.ts

tr -d '\r' < "$SRC/ocr.ts" > "$FORK/src/form/v2/ocr.ts"
echo "copied  src/form/v2/ocr.ts"

python3 - "$CHILD" <<'PYEOF'
import io, sys, re

path = sys.argv[1]
src = io.open(path, encoding="utf-8").read()

if "getOcrPrefillFields" in src:
    print("SKIP    child.ts (already wired)")
    raise SystemExit(0)

# 1. import the module
anchor = "import { applicationConfig } from '@countryconfig/api/application/application-config'"
assert anchor in src, "import anchor not found"
src = src.replace(
    anchor,
    anchor + "\nimport {\n  getOcrPrefillFields,\n  ocrValue\n} from '@countryconfig/form/v2/ocr'",
    1,
)

# 2. let OCR results flow into the fields it can fill. Each is a plain
#    `value:` reference, so the field stays editable and simply starts out
#    populated when a scan produced something for it.
FILLABLE = {
    "child.name": "child.name",
    "child.gender": "child.gender",
    "child.dob": "child.dob",
    "child.placeOfBirth": "child.placeOfBirth",
    "child.birthLocation.other": "child.birthLocation.other",
}
for field_id, ocr_id in FILLABLE.items():
    needle = "      id: '%s',\n" % field_id
    if needle not in src:
        print("WARN    field %s not found, skipped" % field_id)
        continue
    src = src.replace(needle, needle + "      value: ocrValue('%s'),\n" % ocr_id, 1)

# 3. append the panel to the page's field list (last entry before the
#    closing `]\n})` of defineFormPage)
tail = "\n  ]\n})"
assert src.rstrip().endswith("]\n})"), "unexpected end of child.ts"
idx = src.rstrip().rfind(tail)
assert idx != -1
src = src[:idx] + ",\n    ...getOcrPrefillFields()" + src[idx:]

io.open(path, "w", encoding="utf-8").write(src)
print("PATCHED child.ts")
PYEOF

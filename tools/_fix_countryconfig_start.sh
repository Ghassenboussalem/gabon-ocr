#!/bin/bash
# `yarn dev` -> `yarn start` -> `yarn setup-analytics && <server>`, and
# setup-analytics shells out to `docker`, which is only present in the distro
# while Docker Desktop's WSL integration is switched on. That integration
# drops whenever Docker Desktop restarts, and countryconfig then refuses to
# boot even though the analytics database it wants to create already exists.
# Run the server directly and treat the (idempotent) analytics setup as
# best-effort so a missing docker CLI can no longer take the service down.
set -eu
f=/root/run_countryconfig.sh

if grep -q 'best-effort analytics' "$f"; then
  echo "SKIP  run_countryconfig.sh (already patched)"
  exit 0
fi

python3 - "$f" <<'PYEOF'
import io, sys
p = sys.argv[1]
s = io.open(p, encoding="utf-8").read()
old = "yarn dev\n"
new = (
    "# best-effort analytics setup: needs the docker CLI, which is absent\n"
    "# whenever Docker Desktop's WSL integration is off. The database is\n"
    "# created once and survives, so a failure here must not block startup.\n"
    "yarn setup-analytics || echo 'setup-analytics skipped (docker unavailable)'\n"
    "exec yarn cross-env NODE_ENV=development "
    "NODE_OPTIONS=--dns-result-order=ipv4first "
    "nodemon --exec ts-node -r tsconfig-paths/register src/index.ts\n"
)
assert s.endswith(old), "unexpected tail of run_countryconfig.sh"
io.open(p, "w", encoding="utf-8").write(s[: -len(old)] + new)
print("PATCHED run_countryconfig.sh")
PYEOF

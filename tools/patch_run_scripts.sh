#!/bin/bash
# Rend les /root/run_<svc>.sh (distro ubuntu-opencrvs) IDEMPOTENTS :
# avant "yarn start", tuer les processus survivants du MEME package et
# liberer le port. Evite les doublons de port et les watchers gen:types
# dupliques (cause du schema.d.ts corrompu a 0 octet).
#
# Usage (depuis Windows) :
#   wsl -d ubuntu-opencrvs -u root -- bash -c "tr -d '\r' < /mnt/c/Users/Ghassen/Documents/gabon-ocr/tools/patch_run_scripts.sh | bash"
#
# Idempotent : re-executer ne double pas le guard (marqueur "guard idempotence").
set -u

declare -A PORT=(
  [auth]=4040 [user-mgnt]=3030 [workflow]=5050 [search]=9090
  [metrics]=1050 [notification]=2020 [config]=2021 [documents]=9050
  [webhooks]=2525 [events]=5555 [gateway]=7070 [client]=3000
  [login]=3020 [countryconfig]=3040
)

for svc in "${!PORT[@]}"; do
  f=/root/run_$svc.sh
  [ -f "$f" ] || { echo "SKIP   $svc (pas de script)"; continue; }
  if grep -q 'guard idempotence' "$f"; then echo "DEJA   $svc"; continue; fi
  port=${PORT[$svc]}

  # motif pkill avec crochets (ne se matche pas lui-meme) ; pour countryconfig,
  # prefixe /opt/ pour NE PAS matcher le wrapper de la tache planifiee
  # (qui contient /var/log/opencrvs-countryconfig.log)
  if [ "$svc" = countryconfig ]; then
    pat='/opt/opencrvs/opencrvs-countryconfi[g]'
  else
    last=${svc: -1}
    base=${svc%?}
    pat="packages/${base}[${last}]/"
  fi

  extra=""
  if [ "$svc" = gateway ]; then
    extra="pkill -9 -f 'gen:type[s]' 2>/dev/null
pkill -9 -f 'gen:schem[a]' 2>/dev/null"
  fi

  guard=$(cat <<EOF
# --- guard idempotence : tuer les survivants avant de (re)demarrer ---
pkill -9 -f '$pat' 2>/dev/null
$extra
for _i in 1 2 3 4 5; do
  _pids=\$(ss -ltnp "sport = :$port" 2>/dev/null | grep -o 'pid=[0-9]*' | cut -d= -f2 | sort -u)
  [ -z "\$_pids" ] && break
  kill -9 \$_pids 2>/dev/null
  sleep 1
done
# --- fin guard ---
EOF
)

  awk -v g="$guard" 'NR==1{print; print g; next}{print}' "$f" > "$f.tmp" && mv "$f.tmp" "$f" && chmod +x "$f"
  echo "PATCHE $svc (port $port, motif $pat)"
done

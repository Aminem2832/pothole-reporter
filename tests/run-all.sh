#!/usr/bin/env bash
# Every check that guards a shipped behaviour. Needs .env with OPENAI_API_KEY.
# The live ones hit KGIS and OpenAI on purpose: the answers that matter are today's.
set -uo pipefail
cd "$(dirname "$0")/.."
PY=.venv/bin/python3

pkill -f "http.server 8765" >/dev/null 2>&1; sleep 1
(cd android-app/www && nohup python3 -m http.server 8765 >/tmp/pothole-srv.log 2>&1 &)
sleep 2
trap 'pkill -f "http.server 8765" >/dev/null 2>&1' EXIT

fail=0
for t in unit_test ui_text_test routing_test nh_test gis_failure_test footage_test; do
  printf "%-18s " "$t"
  if out=$($PY "tests/$t.py" 2>&1); then
    echo "${out##*$'\n'}"
  else
    echo "FAIL"; echo "$out" | sed 's/^/    /'; fail=1
  fi
done
echo
[ "$fail" = "0" ] && echo "ALL TESTS PASS" || { echo "SOME TESTS FAILED"; exit 1; }

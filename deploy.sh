#!/usr/bin/env bash
# Copy BoardPet onto the ESP32 and restart it. Usage: ./deploy.sh [port]
set -euo pipefail
cd "$(dirname "$0")"
PORT="${1:-/dev/ttyUSB0}"
[ -f config.json ] || { echo "config.json missing: copy config.example.json and fill in your Wi-Fi"; exit 1; }
python3 tests/test_pet.py >/dev/null
gzip -9 -k -f index.html
mpremote connect "$PORT" cp pet.py :pet.py + cp index.html.gz :index.html.gz + cp config.json :config.json + cp main.py :main.py + reset
rm -f index.html.gz
echo "Deployed. Open http://$(python3 -c 'import json;print(json.load(open("config.json"))["hostname"])').local in a minute."

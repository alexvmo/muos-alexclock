#!/bin/sh
# HELP: AlexClock - Часы, дата и погода для muOS
# ICON: default
# GRID: AlexClock

. /opt/muos/script/var/func.sh

SETUP_STAGE_OVERLAY

APP_BIN="python3"
SETUP_APP "$APP_BIN" ""

APP_DIR="$1"
cd "$APP_DIR" || exit

python3 "$APP_DIR/clock.py"

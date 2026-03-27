#!/bin/bash
SCENARIO=${1:-standard}
EXAM=${2:-exam-1}
KEY_PATH=${SSH_KEY_PATH:-$HOME/.ssh/lab_key}
ROOT="$(cd "$(dirname "$0")" && pwd)"
VENV="$ROOT/backend/rhcsa-lab"

if [[ ! -f "$VENV/bin/python3" ]]; then
  echo "ERROR: venv not found at $VENV — run setup.sh first" >&2
  exit 1
fi

echo "Starting RHCSA Lab"
echo "  Scenario : $SCENARIO"
echo "  Exam     : $EXAM"
echo "  SSH Key  : $KEY_PATH"

while true; do
    PROJECT_ROOT=$ROOT \
    ACTIVE_SCENARIO=$SCENARIO \
    ACTIVE_EXAM=$EXAM \
    SSH_KEY_PATH=$KEY_PATH \
    "$VENV/bin/python3" "$ROOT/backend/app.py"
    echo "[run.sh] app.py exited, restarting..."
    sleep 1
done

#!/bin/bash
SCENARIO=${1:-standard}
EXAM=${2:-exam-1}
KEY_PATH=${SSH_KEY_PATH:-$HOME/.ssh/lab_key}
ROOT="$(cd "$(dirname "$0")" && pwd)"

echo "Starting RHCSA Lab"
echo "  Scenario : $SCENARIO"
echo "  Exam     : $EXAM"
echo "  SSH Key  : $KEY_PATH"

cd "$(dirname "$0")/backend"
source rhcsa-lab/bin/activate

while true; do
    PROJECT_ROOT=$ROOT \
    ACTIVE_SCENARIO=$SCENARIO \
    ACTIVE_EXAM=$EXAM \
    SSH_KEY_PATH=$KEY_PATH \
    python3 app.py
    echo "[run.sh] app.py exited, restarting..."
    sleep 1
done

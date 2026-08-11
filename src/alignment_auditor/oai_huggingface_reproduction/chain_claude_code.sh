#!/usr/bin/env bash
# Wait for the react matrix to finish, then run the claude_code matrix (avoids docker
# contention / image-build races from running both at once).
cd "$(dirname "$0")/.."
while pgrep -f "run_matrix.sh react" >/dev/null 2>&1; do sleep 20; done
bash incidents/run_matrix.sh claude_code 8

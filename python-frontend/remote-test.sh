#!/usr/bin/env bash
set -euo pipefail
# Edit locally; sync only the spike. Preserve all remote build artifacts.
here=$(cd -- "$(dirname -- "$0")" && pwd)
# Use the configured host alias so SSH selects id_ed25519_vulcan.
remote=vulcan
root=/home/noir/gibbon-python-mvp
rsync -az --exclude=build/ --exclude=__pycache__/ "$here/" "$remote:$root/python-frontend/"
ssh -o BatchMode=yes "$remote" "cd '$root' && nix-shell python-kernels/shell-sequential.nix --run 'cd python-frontend && python3 -m unittest discover -v && python3 verify_native.py --gibbon ../python-kernels/spikes/native/gibbon --gibbon-root .. && python3 verify_bounds.py --gibbon ../python-kernels/spikes/native/gibbon --gibbon-root .. && python3 verify_decision_trees.py --gibbon ../python-kernels/spikes/native/gibbon --gibbon-root ..'"

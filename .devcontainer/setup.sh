#!/usr/bin/env bash
set -euo pipefail
chmod +x scripts/*.sh
curl -fsSLo /tmp/kind https://kind.sigs.k8s.io/dl/v0.23.0/kind-linux-amd64
sudo install -m 0755 /tmp/kind /usr/local/bin/kind
pip install -q -r aiops/requirements.txt ansible matplotlib pytest
echo "tools ready: $(kind version) | $(kubectl version --client | head -1) | $(helm version --short)"

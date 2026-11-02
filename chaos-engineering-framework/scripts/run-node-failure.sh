#!/usr/bin/env bash
# Node-failure experiment, automated by Ansible. Usage: run-node-failure.sh [label]
source "$(dirname "$0")/lib.sh"
need ansible-playbook kubectl docker python3
cd "$ROOT"
mkdir -p results
ansible-playbook ansible/node-failure.yml -e "label=${1:-$(current_version)}"

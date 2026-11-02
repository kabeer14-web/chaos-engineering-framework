# Short commands for the whole lab.  `make help`
.RECIPEPREFIX := >
.DEFAULT_GOAL := help
EXP ?= pod-kill
V ?= v1

help:        ## show this help
> @grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*## "}{printf "  make %-14s %s\n",$$1,$$2}'
tools:       ## install ansible + python deps for the analyzer (Codespaces)
> pip install -q -r aiops/requirements.txt ansible matplotlib pytest
up:          ## build the complete lab (cluster, monitoring, chaos engine, Argo, app v1)  ~15 min
> ./scripts/up.sh
forward:     ## open UIs on localhost (Grafana 3000, Prometheus 9090, Jaeger 16686, Argo 2746)
> ./scripts/forward.sh
version:     ## switch app version:  make version V=v1|v2
> ./scripts/switch-version.sh $(V)
experiment:  ## one experiment via Argo:  make experiment EXP=pod-kill|network-delay|cpu-stress
> ./scripts/run-argo.sh $(EXP)
node-failure: ## node failure experiment via Ansible
> ./scripts/run-node-failure.sh
suite:       ## full before/after study (v1 and v2, 4 experiments each)  ~45 min
> ./scripts/run-suite.sh
compare:     ## results table + chart from results/*.json
> python3 aiops/compare.py
test:        ## unit tests of the AIOps analyzer
> python3 -m pytest -q tests
status:      ## what is running
> kubectl get nodes -L lab.role && kubectl -n app get pods -o wide && kubectl get podchaos,networkchaos,stresschaos -A
down:        ## delete the cluster
> ./scripts/down.sh
.PHONY: help tools up forward version experiment node-failure suite compare test status down

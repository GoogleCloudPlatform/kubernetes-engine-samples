# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

PROJECT_ID ?= $(shell gcloud config get-value project 2>/dev/null)
REGION     ?= us-central1
REGISTRY   ?= $(REGION)-docker.pkg.dev/$(PROJECT_ID)/anthropic-agents
TAG        ?= $(shell git rev-parse --short HEAD 2>/dev/null || date +%Y%m%d)
OVERLAY    ?= 01_single_session
CLUSTER    ?= anthropic-agent-sandbox
ENV_ID     ?= $(ANTHROPIC_ENVIRONMENT_ID)
SESSION_BUCKET ?= $(PROJECT_ID)-claude-session-outputs

SECRETS := anthropic-environment-key anthropic-api-key

.PHONY: env infra creds images deploy destroy

env:
	@test -f .env || { echo "→ run:  cp .env.example .env  # then edit and  source .env"; exit 1; }
	@test -n "$(TF_VAR_project_id)" || { echo "→ run:  source .env"; exit 1; }

infra: env
	cd terraform && terraform init && terraform apply

creds:
	gcloud container clusters get-credentials $(CLUSTER) \
	  --region $(REGION) --project $(PROJECT_ID)

images:
	gcloud builds submit . \
	  --config cloudbuild.yaml \
	  --substitutions _TAG=$(TAG),_REGISTRY=$(REGISTRY) \
	  --region $(REGION) --project $(PROJECT_ID)

define PARAMS_YAML
apiVersion: v1
kind: ServiceAccount
metadata:
  name: dispatcher
  annotations:
    iam.gke.io/gcp-service-account: anthropic-dispatcher@$(PROJECT_ID).iam.gserviceaccount.com
---
apiVersion: v1
kind: ServiceAccount
metadata:
  name: stats-adapter
  annotations:
    iam.gke.io/gcp-service-account: anthropic-stats-adapter@$(PROJECT_ID).iam.gserviceaccount.com
---
apiVersion: v1
kind: ServiceAccount
metadata:
  name: claude-agent-worker
  annotations:
    iam.gke.io/gcp-service-account: anthropic-worker@$(PROJECT_ID).iam.gserviceaccount.com
endef
export PARAMS_YAML

deploy: env creds
	@test -n "$(ENV_ID)" || { echo "ANTHROPIC_ENVIRONMENT_ID is empty — source .env"; exit 1; }
	kubectl get namespace agent-sandbox >/dev/null 2>&1 || kubectl create namespace agent-sandbox
	@for s in $(SECRETS); do \
	  v=$$(gcloud secrets versions access latest --secret $$s --project $(PROJECT_ID)) || exit 1; \
	  kubectl -n agent-sandbox create secret generic $$s \
	    --from-literal=latest="$$v" --dry-run=client -o yaml | kubectl apply -f -; \
	done
	printf '%s\n' "$$PARAMS_YAML" > deploy/overlays/$(OVERLAY)/params.yaml
	printf 'environment_id=%s\nsession_bucket=%s\n' "$(ENV_ID)" "$(SESSION_BUCKET)" > deploy/overlays/$(OVERLAY)/params.env
	cd deploy/overlays/$(OVERLAY) && \
	kustomize edit set image \
	  claude-agent-worker=$(REGISTRY)/claude-agent-worker:$(TAG) \
	  anthropic-dispatcher=$(REGISTRY)/anthropic-dispatcher:$(TAG) \
	  anthropic-stats-adapter=$(REGISTRY)/anthropic-stats-adapter:$(TAG) && \
	kustomize build . | kubectl apply -f - && \
	git checkout -- kustomization.yaml 2>/dev/null || true

destroy: env
	cd terraform && terraform destroy

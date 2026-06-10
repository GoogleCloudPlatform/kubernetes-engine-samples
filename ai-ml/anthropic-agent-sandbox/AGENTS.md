# AGENTS.md

Guidance for AI coding agents working in this directory.

## What this is

A reference implementation of Anthropic Managed Agents **self-hosted
sandboxes** on GKE. The agent loop and model stay on Anthropic; only the
sandbox (tool execution) runs here, in gVisor pods. Three small containers
(`src/worker`, `src/dispatcher`, `src/stats-adapter`), Terraform for the
cluster + bucket, Kustomize for the manifests.

## Layout

| Path | Purpose | Edit when |
| --- | --- | --- |
| `terraform/` | GKE Autopilot, Agent Sandbox add-on, AR, Secret Manager, GCS session-outputs bucket, WIF | infra shape changes |
| `deploy/base/` | SandboxTemplate (with GCS FUSE volume), WarmPool, NetworkPolicy, KSAs, Deployments, RBAC | k8s resource changes |
| `deploy/overlays/NN_*/` | per-scenario Kustomize patches | adding a scenario |
| `src/worker/` | gVisor sandbox image; entrypoint waits for dispatch then exec's `ant beta:worker run` | tool runtime changes |
| `src/dispatcher/` | polls Anthropic work queue → `SandboxClaim` → POST session to warm pod | claim/queue logic |
| `src/stats-adapter/` | reads `work.stats` → Cloud Monitoring + `SandboxWarmPool/scale` | autoscale logic |
| `scripts/fire_session.py` | local smoke test (creates agent + session, prints events) | smoke-test changes |

## Build, deploy, test

All commands assume `cp .env.example .env`, values filled in, `source .env`.

| Goal | Command |
| --- | --- |
| Validate Terraform | `cd terraform && terraform init && terraform validate` |
| Validate manifests | `kustomize build deploy/overlays/01_single_session > /dev/null` (needs `params.yaml`/`params.env` — `make deploy` generates them) |
| Build all images | `make images` (Cloud Build; never `docker build` locally) |
| Rebuild one image | `gcloud builds submit src/<dir> --tag $REGISTRY/<image>:$TAG --region $REGION` — `<dir>`→`<image>`: `worker`→`claude-agent-worker`, `dispatcher`→`anthropic-dispatcher`, `stats-adapter`→`anthropic-stats-adapter` |
| Deploy / redeploy | `make deploy OVERLAY=01_single_session` (or `02_warmpool_autoscale`) |
| Smoke test | `uv run scripts/fire_session.py` — pass when output contains `4.4.0` (gVisor kernel) and `"type":"end_turn"` |
| Verify session storage | Send a prompt that writes to `/mnt/session/outputs/probe.txt`, then `gcloud storage cat gs://$SESSION_BUCKET/$SESSION_ID/probe.txt` |
| Pick up a code change in-cluster | rebuild that image, then `kubectl -n agent-sandbox rollout restart deploy/<name>` (`imagePullPolicy: Always`) |
| Tear down | `make destroy` |

## Conventions

- Python 3.12, `uv` for dependency management. No `pip install` in docs.
- All knobs via `argparse` + env-var defaults; no hard-coded project IDs,
  regions, or model names.
- k8s parameterization via Kustomize overlays only — never `sed`/`envsubst`.
- New overlays: `deploy/overlays/NN_<what_changed>/`.
- Container images build via Cloud Build (`cloudbuild.yaml`), not local Docker.
- Apache 2.0 header (`Copyright <year> Google LLC`) on every `.py`, `.tf`,
  `.yaml`, `Dockerfile`, `Makefile`.
- The org-scoped `ANTHROPIC_API_KEY` must never reach `src/worker/` or
  `deploy/base/sandbox-template.yaml`. Only the environment key
  (`ANTHROPIC_ENVIRONMENT_KEY`) goes into the sandbox.

## Implementation notes

These work around upstream behavior; do not refactor without re-testing:

- `src/dispatcher/main.py` reads the bound pod IP from the core API, **not**
  `sb.get_pod_ip()` (returns `None` on GKE) and **not** the per-claim Service
  DNS (too fresh to resolve).
- `deploy/base/fqdn-egress.yaml` pairs `FQDNNetworkPolicy` with a default-deny
  `NetworkPolicy`; the FQDN policy alone is not a deny.
- `deploy/base/sandbox-template.yaml` sets `runAsUser: 1000` alongside
  `runAsNonRoot: true`; with only the latter and a named `USER` in the
  Dockerfile the pod fails `CreateContainerConfigError`.
- `Makefile` pipes `kustomize build | kubectl apply -f -` rather than
  `kubectl apply -k`; kubectl's bundled kustomize rejects the multi-doc patch
  in `params.yaml`.
- `deploy/base/kustomize-config.yaml` teaches Kustomize where the image field
  lives inside `SandboxTemplate`; without it `kustomize edit set image` skips
  the worker.
- `src/dispatcher/main.py` `reap_stale_claims()` + `--max-redispatch` guard
  against re-offered work items for deleted sessions; removing either re-opens
  a claim leak / scale-down stall.
- `deploy/base/fqdn-egress.yaml` includes `169.254.169.254/32:80` egress for
  the GCS FUSE sidecar; the per-volume opt-out is currently clobbered by the
  driver, so removing this rule breaks the bucket mount.
- `entrypoint.py` symlinks `/mnt/session/outputs` → `/mnt/gcs/<session_id>`
  *after* dispatch — same late-binding reason as the session ID itself.

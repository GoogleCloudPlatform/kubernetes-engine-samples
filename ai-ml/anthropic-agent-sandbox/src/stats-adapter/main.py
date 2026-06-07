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

"""Publish work.stats to Cloud Monitoring and patch SandboxWarmPool/scale. Only holder of ANTHROPIC_API_KEY."""
import argparse
import logging
import os
import time

import anthropic
from google.cloud import monitoring_v3

log = logging.getLogger("stats-adapter")

METADATA_PROJECT_URL = (
    "http://metadata.google.internal/computeMetadata/v1/project/project-id"
)


def parse_args():
    """Parse CLI flags, with defaults from the matching env vars."""
    p = argparse.ArgumentParser()
    p.add_argument("--environment-id", default=os.environ.get("ANTHROPIC_ENVIRONMENT_ID"))
    p.add_argument("--project-id", default=os.environ.get("PROJECT_ID"))
    p.add_argument("--metric-type",
                   default=os.environ.get("METRIC_TYPE", "custom.googleapis.com/anthropic/work_depth"))
    p.add_argument("--interval", type=int,
                   default=int(os.environ.get("POLL_INTERVAL_SECONDS", "15")))
    p.add_argument("--direct-patch", action="store_true",
                   default=os.environ.get("DIRECT_PATCH", "").lower() == "true")
    p.add_argument("--warmpool", default=os.environ.get("SANDBOX_WARMPOOL", "claude-agent-worker"))
    p.add_argument("--namespace", default=os.environ.get("SANDBOX_NAMESPACE", "agent-sandbox"))
    p.add_argument("--min-replicas", type=int, default=int(os.environ.get("WARMPOOL_MIN", "2")))
    p.add_argument("--max-replicas", type=int, default=int(os.environ.get("WARMPOOL_MAX", "50")))
    return p.parse_args()


def resolve_project_id(explicit: str | None) -> str:
    """Return the explicit project ID, or read it from the GCE metadata server."""
    if explicit:
        return explicit
    import urllib.request
    req = urllib.request.Request(METADATA_PROJECT_URL, headers={"Metadata-Flavor": "Google"})
    with urllib.request.urlopen(req, timeout=2) as r:
        return r.read().decode()


def write_gauge(client, project, metric_type, environment_id, value: int):
    """Write one int64 gauge point to Cloud Monitoring, labelled by environment_id."""
    series = monitoring_v3.TimeSeries()
    series.metric.type = metric_type
    series.metric.labels["environment_id"] = environment_id
    series.resource.type = "global"
    now = time.time()
    point = monitoring_v3.Point(
        interval=monitoring_v3.TimeInterval(end_time={"seconds": int(now), "nanos": int((now % 1) * 1e9)}),
        value=monitoring_v3.TypedValue(int64_value=value),
    )
    series.points = [point]
    client.create_time_series(name=f"projects/{project}", time_series=[series])


def main():
    """Publish work.stats every interval and (optionally) patch the warm pool /scale."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", force=True)
    args = parse_args()
    if not args.environment_id:
        raise SystemExit("ANTHROPIC_ENVIRONMENT_ID is not set")
    project = resolve_project_id(args.project_id)
    ant = anthropic.Anthropic()  # ANTHROPIC_API_KEY from env
    mon = monitoring_v3.MetricServiceClient()

    k8s = None
    if args.direct_patch:
        from kubernetes import client, config
        config.load_incluster_config()
        k8s = client.CustomObjectsApi()

    log.info("env=%s project=%s direct_patch=%s warmpool=%s/%s",
             args.environment_id, project, args.direct_patch, args.namespace, args.warmpool)

    last_target = None
    while True:
        try:
            stats = ant.beta.environments.work.stats(environment_id=args.environment_id)
            # depth drains <1s once warm pods exist; depth+pending == concurrent sessions.
            depth = stats.depth + stats.pending
            write_gauge(mon, project, args.metric_type, args.environment_id, depth)

            if k8s is not None:
                target = max(args.min_replicas, min(args.max_replicas, depth))
                if target != last_target:
                    k8s.patch_namespaced_custom_object_scale(
                        group="extensions.agents.x-k8s.io",
                        version="v1alpha1",
                        namespace=args.namespace,
                        plural="sandboxwarmpools",
                        name=args.warmpool,
                        body={"spec": {"replicas": target}},
                    )
                    log.info("depth=%d pending=%d -> scale %s replicas %s -> %d",
                             stats.depth, stats.pending, args.warmpool, last_target, target)
                    last_target = target
                else:
                    log.debug("depth=%d pending=%d target=%d (unchanged)", stats.depth, stats.pending, target)
        except Exception as e:
            log.warning("tick failed: %s", e)

        time.sleep(args.interval)


if __name__ == "__main__":
    main()

# Copyright 2026 Google LLC. All rights reserved.
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

"""Cluster shape helpers -- the one place the course reads the hardware.

No notebook hardcodes a GPU count or an instance type. Every worker count is
derived from the live cluster at runtime, so the same notebooks run unchanged
on any of the validated shapes:

    4 GPUs    = 1 x g4dn.12xlarge   (4 T4s on ONE node -- the reference config)
    4 GPUs    = 1 x g6.12xlarge     (4 L4s on ONE node)
    2-4 GPUs  = 2-4 x g7e.4xlarge   (1 GPU per node)

GPU count is not the binding constraint -- *host* RAM is. Notebook 03 needs
~48 GB of host RAM per GPU, so the common 32 GB single-GPU shapes
(g4dn.2xlarge, g5.2xlarge, g7.2xlarge) get through 00-02 on a fresh cluster and
are then OOM-killed in 03. Pick the instance on host RAM; see "Instance types"
in the README for the full table.

That is also why this module reports GPUs *per node* as well as the total: model
staging and host-memory budgeting are per node, while train and sim worker
counts are per GPU.

Usage in a notebook, after `ray.init(...)`:

    from tools import cluster
    cluster.describe()                       # print the shape + any warnings
    NUM_TRAIN_WORKERS = cluster.train_workers()   # one DDP worker per GPU
    SIM_WORKERS       = cluster.sim_workers()      # one rollout per GPU node

Only depends on `ray` -- safe to import from any notebook, including the
overview, without pulling in torch.
"""

import os


def _ray():
    import ray
    if not ray.is_initialized():
        raise RuntimeError(
            "Ray is not initialized. Run the ray.init(...) cell above first."
        )
    return ray


def topology():
    """Describe the live cluster: totals plus a per-node breakdown.

    Returns a dict::

        {"gpus": 4, "cpus": 48, "nodes": 1, "gpu_nodes": 1,
         "accelerator": "L4",
         "per_node": [{"host": ..., "gpus": 4, "cpus": 48,
                       "memory_gib": 134.2, "accelerator": "L4"}, ...]}

    `accelerator` comes from Ray's `accelerator_type:<NAME>` node resource, so
    the notebooks can *report* the GPU model without ever pinning one.
    """
    ray = _ray()
    res = ray.cluster_resources()
    per_node = []
    for n in ray.nodes():
        if not n.get("Alive"):
            continue
        r = n.get("Resources", {})
        gpus = int(r.get("GPU", 0))
        if not gpus:
            continue
        accel = next((k.split(":", 1)[1] for k in r
                      if k.startswith("accelerator_type:")), None)
        per_node.append({
            "host": n.get("NodeManagerHostname", n.get("NodeID", "?")[:8]),
            "gpus": gpus,
            "cpus": int(r.get("CPU", 0)),
            "memory_gib": r.get("memory", 0) / 1024 ** 3,
            "accelerator": accel,
        })
    per_node.sort(key=lambda d: d["host"])
    accels = {d["accelerator"] for d in per_node if d["accelerator"]}
    return {
        "gpus": int(res.get("GPU", 0)),
        "cpus": int(res.get("CPU", 0)),
        "nodes": len([n for n in ray.nodes() if n.get("Alive")]),
        "gpu_nodes": len(per_node),
        "accelerator": "+".join(sorted(accels)) if accels else None,
        "per_node": per_node,
    }


def num_gpus(default=1):
    """Total GPUs Ray can see right now (never less than `default`).

    `cluster_resources()` counts the nodes that are alive at this instant, so on
    an autoscaling cluster this reflects the workers currently attached.
    """
    return max(default, int(_ray().cluster_resources().get("GPU", 0)))


def gpus_per_node():
    """Max GPUs on any single GPU node (4 on g6.12xlarge, 1 on g5.2xlarge)."""
    per_node = topology()["per_node"]
    return max((d["gpus"] for d in per_node), default=1)


def train_workers(env_var="NUM_WORKERS", cap=None):
    """How many Ray Train workers to launch: one per GPU.

    `ScalingConfig(num_workers=train_workers())` is the whole scaling story --
    2 GPUs, 4 GPUs, or 400 all take the same line. An explicit `NUM_WORKERS`
    environment variable wins, so a run can be pinned smaller than the cluster.
    """
    override = os.environ.get(env_var)
    if override:
        return max(1, int(override))
    n = num_gpus()
    return min(n, cap) if cap else n


def sim_workers(reserve_for_serve=1, env_var="SIM_WORKERS"):
    """Parallel Isaac Lab rollouts to fan out (notebook 03).

    Two limits, and we take the smaller:

    * **GPUs.** The Serve policy replica holds one GPU for the whole sim phase
      and each sim worker takes one more, so the ceiling is
      `GPUs - reserve_for_serve`.
    * **Nodes.** One rollout per GPU node. Isaac Sim boots its own Kit runtime
      per process and shares an extension cache per node, so one boot at a time
      per node is the arrangement this course is validated on.

    That gives 1 rollout on a 2-GPU cluster, 3 across four single-GPU nodes, and
    1 on a single 4-GPU node such as a g6.12xlarge. Set `SIM_WORKERS` to fan out
    further on one node: startup is serialized by `franka_env.kit_startup_lock`,
    so the boots queue and the rollouts still run in parallel once they are up.
    """
    override = os.environ.get(env_var)
    if override:
        return max(1, int(override))
    by_gpu = num_gpus() - reserve_for_serve
    by_node = topology()["gpu_nodes"]
    return max(1, min(by_gpu, by_node))


def describe(print_fn=print):
    """Print the cluster shape and the worker counts derived from it.

    This is the 'what am I running on' cell every notebook opens with, in place
    of a hardcoded 'you should see 2 GPUs'. Returns the topology dict.
    """
    topo = topology()
    accel = topo["accelerator"] or "unknown model"
    shape = (f"{topo['gpus']} GPU(s) ({accel}) across {topo['gpu_nodes']} GPU "
             f"node(s), {topo['cpus']} CPUs total")
    print_fn(f"Cluster: {shape}")
    for d in topo["per_node"]:
        print_fn(f"  {d['host']}: {d['gpus']} x {d['accelerator'] or 'GPU'}, "
                 f"{d['cpus']} CPU, {d['memory_gib']:.0f} GiB Ray memory")
    print_fn(f"Derived: train workers = {train_workers()}, "
             f"sim workers (nb03) = {sim_workers()}")
    return topo

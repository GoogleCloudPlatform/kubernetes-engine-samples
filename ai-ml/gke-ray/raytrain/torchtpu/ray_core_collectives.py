# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# [START gke_ai_ml_gke_ray_raytrain_torchtpu_ray_core_collectives]
import argparse
import math
import os

import ray
from ray.util.tpu import run_on_slice, slice_placement_group
import torch
import torch.distributed as dist
from torch.distributed.device_mesh import init_device_mesh
from torch.distributed.tensor.parallel import (
    ColwiseParallel,
    RowwiseParallel,
    parallelize_module,
)
import torch.nn as nn
import torch_tpu  # noqa: F401 - registers the 'tpu' device and 'tpu_dist' backend

os.environ["RAY_DEDUP_LOGS"] = "0"

RANDOM_SEED = 42


class FeedForward(nn.Module):
    """Two-layer feed-forward block for tensor-parallel sharding across a TPU slice."""

    def __init__(self, hidden_dim: int):
        super().__init__()
        self.w1 = nn.Linear(hidden_dim, 4 * hidden_dim, bias=False)
        self.act = nn.SiLU()
        self.w2 = nn.Linear(4 * hidden_dim, hidden_dim, bias=False)
        with torch.no_grad():
            self.w1.weight.normal_(std=1.0 / math.sqrt(hidden_dim))
            self.w2.weight.normal_(std=1.0 / math.sqrt(4 * hidden_dim))

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return x + self.w2(self.act(self.w1(x)))


@ray.remote
class TorchTPUSliceWorker:
    """Ray actor bound to a single logical TPU device within a slice placement group."""

    def __init__(
        self,
        env_vars_by_rank: list[dict[str, str]],
        devices_per_host: int,
    ):
        self.node_ip = ray.util.get_node_ip_address()
        hosts = env_vars_by_rank[0]["TPU_WORKER_HOSTNAMES"].split(",")
        self.worker_id = hosts.index(self.node_ip)
        tpu_ids = ray.get_runtime_context().get_accelerator_ids().get("TPU", ["0"])
        self.local_rank = int(tpu_ids[0])
        self.rank = self.worker_id * devices_per_host + self.local_rank
        os.environ.update(env_vars_by_rank[self.rank])

    def run_tensor_parallel_step(
        self,
        batch_size: int = 64,
        hidden_dim: int = 128,
    ) -> dict:
        if not dist.is_initialized():
            dist.init_process_group(backend="tpu_dist")

        world_size = dist.get_world_size()
        device = torch.device("tpu")

        # 1. Compute single-device reference output on CPU (rank 0) with identical seed.
        torch.manual_seed(RANDOM_SEED)
        ref_model = FeedForward(hidden_dim).eval()
        inputs_cpu = torch.randn(batch_size, hidden_dim)
        with torch.no_grad():
            ref_output = ref_model(inputs_cpu) if self.rank == 0 else None

        # 2. Shard the model across all TPU devices in the slice with DTensor TP.
        torch.manual_seed(RANDOM_SEED)
        tp_model = FeedForward(hidden_dim).to(device).eval()
        mesh = init_device_mesh("tpu", (world_size,))
        tp_plan = {
            "w1": ColwiseParallel(),
            "w2": RowwiseParallel(),
        }
        tp_model = parallelize_module(
            tp_model,
            mesh,
            tp_plan,
            src_data_rank=0,
        )

        with torch.no_grad():
            tp_output = tp_model(inputs_cpu.to(device)).cpu()

        max_abs_diff = 0.0
        if self.rank == 0 and ref_output is not None:
            torch.testing.assert_close(tp_output, ref_output, rtol=1e-3, atol=1e-2)
            max_abs_diff = float((tp_output - ref_output).abs().max().item())

        # 3. Verify direct ICI all_reduce across all ranks in the slice.
        rank_tensor = torch.ones((4,), dtype=torch.float32, device=device) * (
            self.rank + 1
        )
        dist.all_reduce(rank_tensor, op=dist.ReduceOp.SUM)
        all_reduce_sum = rank_tensor.cpu().tolist()

        dist.destroy_process_group()
        return {
            "rank": self.rank,
            "local_rank": self.local_rank,
            "worker_id": self.worker_id,
            "node_ip": self.node_ip,
            "all_reduce_sum": all_reduce_sum,
            "max_abs_diff": max_abs_diff,
        }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run distributed TorchTPU tensor parallelism across a Ray TPU slice."
    )
    parser.add_argument(
        "--topology",
        type=str,
        default="4x4",
        help="TPU physical topology (for example, '4x4' for v6e or '2x2x2' for TPU7x).",
    )
    parser.add_argument(
        "--accelerator-type",
        type=str,
        default="TPU-V6E",
        help="Ray TPU accelerator type (for example, 'TPU-V6E' or 'TPU-V7X').",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    ray.init()

    accelerator_version = args.accelerator_type.upper().removeprefix("TPU-").lower()
    slice_handle = slice_placement_group(
        topology=args.topology,
        accelerator_version=accelerator_version,
        num_slices=1,
        resources_per_bundle={"TPU": 1},
    )
    ray.get(slice_handle.placement_group.ready())

    print(
        f"Reserved slice placement group: topology={args.topology}, "
        f"accelerator_type={args.accelerator_type}, "
        f"num_bundles={slice_handle.num_bundles}, "
        f"num_hosts={slice_handle.num_hosts}"
    )

    env_vars_by_rank = [
        slice_handle.get_torchtpu_env_vars(rank=r)
        for r in range(slice_handle.num_bundles)
    ]
    workers = run_on_slice(
        TorchTPUSliceWorker,
        env_vars_by_rank,
        slice_handle.devices_per_host,
        tpu_slice=slice_handle,
    )
    results = sorted(
        ray.get([w.run_tensor_parallel_step.remote() for w in workers]),
        key=lambda r: r["rank"],
    )

    expected_sum = sum(range(1, slice_handle.num_bundles + 1))
    for r in results:
        print(
            f"Rank {r['rank']:2d} (worker_id={r['worker_id']}, "
            f"local_rank={r['local_rank']}, ip={r['node_ip']}): "
            f"all_reduce_sum={r['all_reduce_sum']}"
        )
        assert r["all_reduce_sum"] == [float(expected_sum)] * 4

    print(
        f"SUCCESS: All {len(results)} TorchTPU ranks verified DTensor TP parity "
        f"(max_abs_diff={results[0]['max_abs_diff']:.6f}) and "
        f"all_reduce sum = {expected_sum:.1f}"
    )
    for w in workers:
        ray.kill(w)
    slice_handle.shutdown()


if __name__ == "__main__":
    main()
# [END gke_ai_ml_gke_ray_raytrain_torchtpu_ray_core_collectives]

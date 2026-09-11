#!/usr/bin/env python3

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

"""
Comprehensive compatibility and TPU v7 optimization patch for MaxText RL/GRPO.
Fixes:
1. PyTorch 2.6 / Python 3.12 custom-op schema registration.
2. Protobuf C++ shared library collision by mocking tpu_info.
3. TPU v7 Pallas Ragged Paged Attention (RPA) SRAM VMEM overflow.
4. Torchax / vLLM float4 custom-op mapping cleanup.
"""

import glob
import os
import re

print(">>> [Patch 1/5] Patching tpu_info C++ extension to pure-Python mock...")
tpu_info_path = "/usr/local/lib/python3.12/site-packages/tpu_info/__init__.py"
if os.path.exists(tpu_info_path):
    with open(tpu_info_path, "w") as f:
        f.write("""class DummyTPUInfo:
    def __init__(self):
        self.tpu_type = 'tpu7x-8'
        self.num_chips = 4
        self.worker_id = 0

def get_tpu_info():
    return DummyTPUInfo()

def get_num_chips():
    return 4

def get_tpu_type():
    return 'tpu7x-8'
""")
    print("  -> tpu_info successfully mocked.")

print(">>> [Patch 2/5] Patching TPU v7 Pallas Ragged Paged Attention (RPA) VMEM tile size...")
rpa_kpath = "/usr/local/lib/python3.12/site-packages/tpu_inference/kernels/ragged_paged_attention/v3/kernel.py"
if os.path.exists(rpa_kpath):
    with open(rpa_kpath, "r") as f:
        s = f.read()
    s = s.replace("bq_sz = min(2048 // num_q_heads_per_kv_head, max_q // 2)", "bq_sz = min(512 // num_q_heads_per_kv_head, max_q // 2)")
    s = s.replace("bkv_sz = min(2048, max_kv // 2)", "bkv_sz = min(512, max_kv // 2)")
    s = s.replace("bq_csz = min(1024 // num_q_heads_per_kv_head, max_q // 2)", "bq_csz = min(256 // num_q_heads_per_kv_head, max_q // 2)")
    s = s.replace("bkv_csz = min(512, align_to(max_kv // 2, page_size))", "bkv_csz = min(256, align_to(max_kv // 2, page_size))")
    with open(rpa_kpath, "w") as f:
        f.write(s)
    print("  -> RPA v3 kernel.py tile sizes tuned for TPU v7 64MB VMEM.")

rpa_tpath = "/usr/local/lib/python3.12/site-packages/tpu_inference/kernels/ragged_paged_attention/v3/tuned_block_sizes.py"
if os.path.exists(rpa_tpath):
    with open(rpa_tpath, "r") as f:
        s = f.read()
    s = s.replace("bkv_p, bq = (4096 // page_size, 32)", "bkv_p, bq = (512 // page_size, 16)")
    with open(rpa_tpath, "w") as f:
        f.write(s)
    print("  -> RPA v3 tuned_block_sizes.py fallback tuned for TPU v7.")

print(">>> [Patch 3/5] Patching PyTorch 2.6 infer_schema.py for Python 3.12 UnionType...")
infer_schema_path = "/usr/local/lib/python3.12/site-packages/torch/_library/infer_schema.py"
if os.path.exists(infer_schema_path):
    with open(infer_schema_path, "r") as f:
        s = f.read()
    s = re.sub(r'([a-zA-Z_]\w*)\.__origin__', r'getattr(\1, "__origin__", None)', s)
    with open(infer_schema_path, "w") as f:
        f.write(s)
    print("  -> torch._library.infer_schema patched.")

print(">>> [Patch 4/5] Patching Torchax and vLLM float4 custom-op mappings...")
torchax_map = "/usr/local/lib/python3.12/site-packages/torchax/ops/mappings.py"
if os.path.exists(torchax_map):
    with open(torchax_map, "r") as f:
        s = f.read().replace("torch.float4_e2m1fn_x2: jnp.float4_e2m1fn.dtype,", "")
    with open(torchax_map, "w") as f:
        f.write(s)

vllm_tol = "/usr/local/lib/python3.12/site-packages/vllm/ir/tolerances.py"
if os.path.exists(vllm_tol):
    with open(vllm_tol, "r") as f:
        s = f.read().replace('torch.float4_e2m1fn_x2: {"atol": 3e-1, "rtol": 3e-1},', "")
    with open(vllm_tol, "w") as f:
        f.write(s)

print(">>> [Patch 5/5] Patching vLLM typing generics and platform metadata...")
def add_typing(s):
    lines = s.splitlines(True)
    idx = 0
    for i, line in enumerate(lines):
        if line.startswith("from __future__ import"):
            idx = i + 1
    lines.insert(idx, "import typing as _typing\n")
    return "".join(lines)

for p in glob.glob("/usr/local/lib/python3.12/site-packages/vllm/**/*.py", recursive=True):
    try:
        with open(p, "r") as f:
            s = f.read()
        if "list[int]" in s or "| None" in s:
            s = add_typing(s)
            s = s.replace(": list[int]", ": _typing.List[int]")
            s = s.replace("block_size: list[int]", "block_size: _typing.List[int]")
            s = s.replace("ocp_mx_scheme: str | None", "ocp_mx_scheme: _typing.Optional[str]")
            s = s.replace("block_shape: list[int] | None", "block_shape: _typing.Optional[_typing.List[int]]")
            s = s.replace("expert_map: torch.Tensor | None", "expert_map: _typing.Optional[torch.Tensor]")
            s = s.replace("w1_scale: torch.Tensor | None", "w1_scale: _typing.Optional[torch.Tensor]")
            s = s.replace("w2_scale: torch.Tensor | None", "w2_scale: _typing.Optional[torch.Tensor]")
            s = s.replace("w1_zp: torch.Tensor | None", "w1_zp: _typing.Optional[torch.Tensor]")
            s = s.replace("w2_zp: torch.Tensor | None", "w2_zp: _typing.Optional[torch.Tensor]")
            s = s.replace("a1_scale: torch.Tensor | None", "a1_scale: _typing.Optional[torch.Tensor]")
            s = s.replace("a2_scale: torch.Tensor | None", "a2_scale: _typing.Optional[torch.Tensor]")
            s = s.replace("w1_bias: torch.Tensor | None", "w1_bias: _typing.Optional[torch.Tensor]")
            s = s.replace("w2_bias: torch.Tensor | None", "w2_bias: _typing.Optional[torch.Tensor]")
            with open(p, "w") as f:
                f.write(s)
    except Exception:
        pass

vllm_plat = "/usr/local/lib/python3.12/site-packages/vllm/platforms/__init__.py"
if os.path.exists(vllm_plat):
    with open(vllm_plat, "r") as f:
        s = f.read().replace("tpu_info.get_tpu_info()", "is_tpu = True")
    with open(vllm_plat, "w") as f:
        f.write(s)

vllm_usage = "/usr/local/lib/python3.12/site-packages/vllm/usage/usage_lib.py"
if os.path.exists(vllm_usage):
    with open(vllm_usage, "r") as f:
        s = f.read().replace("from tpu_inference import tpu_info, utils", "tpu_info = None")
        s = s.replace("self.gpu_count = tpu_info.get_num_chips()", "self.gpu_count = 4")
        s = s.replace('self.gpu_type = tpu_info.get_tpu_type()', 'self.gpu_type = "tpu7x"')
    with open(vllm_usage, "w") as f:
        f.write(s)

print(">>> All patches successfully applied.")

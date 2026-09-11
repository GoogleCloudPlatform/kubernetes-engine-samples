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
Model FLOPs Utilization (MFU) Calculator for MaxText RL/GRPO on Google Cloud TPU v7x.

Hardware Topology:
    1 VM with 4 TPU v7 Chips (8 Tensor Cores total, 2 cores per chip).
    Peak BF16 Performance per Chip: 2,307 TFLOPs/s.
    Total Theoretical Peak Performance: 4 * 2,307 = 9,228 TFLOPs/s.

Usage:
    # Run post-training with default benchmark baseline
    python3 calculate_mfu.py

    # Or pass custom run step time and batch parameters
    python3 calculate_mfu.py --step-time 6.51 --batch-size 1 --num-generations 2
"""

import argparse

def compute_llama_grpo_mfu(
    num_params_b=8.03,
    seq_len=1024,
    batch_size=1,
    num_generations=2,
    step_time_s=6.51,
    num_tpu_chips=4,
    peak_tflops_per_chip=2307.0
):
    N = num_params_b * 1e9
    total_tokens = batch_size * seq_len * num_generations

    # 1. Rollout Generation (vLLM Sampler): 2 * N FLOPs/token
    rollout_flops = 2.0 * N * total_tokens
    
    # 2. Reference Model Log-probs (Trainer): 2 * N FLOPs/token
    ref_flops = 2.0 * N * total_tokens
    
    # 3. Policy Model Optimization (Trainer Forward + Backward): 6 * N FLOPs/token
    policy_train_flops = 6.0 * N * total_tokens
    
    total_flops = rollout_flops + ref_flops + policy_train_flops
    total_tflops = total_flops / 1e12
    
    achieved_tflops_per_sec = total_tflops / step_time_s
    total_peak_tflops = num_tpu_chips * peak_tflops_per_chip
    mfu_percent = (achieved_tflops_per_sec / total_peak_tflops) * 100.0
    
    return {
        "num_params_b": num_params_b,
        "batch_size": batch_size,
        "num_generations": num_generations,
        "seq_len": seq_len,
        "total_tokens_per_step": total_tokens,
        "step_time_s": step_time_s,
        "total_tflops_per_step": total_tflops,
        "achieved_tflops_s": achieved_tflops_per_sec,
        "total_peak_tflops": total_peak_tflops,
        "mfu_percent": mfu_percent,
        "tflops_per_chip": achieved_tflops_per_sec / num_tpu_chips
    }

def main():
    parser = argparse.ArgumentParser(description="Calculate MFU for LLaMA GRPO RL on Google Cloud TPU v7x.")
    parser.add_argument("--params-b", type=float, default=8.03, help="Model parameters in billions (default: 8.03 for Llama 3.1 8B)")
    parser.add_argument("--seq-len", type=int, default=1024, help="Sequence length in tokens (default: 1024)")
    parser.add_argument("--batch-size", type=int, default=1, help="Per-device batch size (default: 1)")
    parser.add_argument("--num-generations", type=int, default=2, help="Number of rollouts per prompt (default: 2)")
    parser.add_argument("--step-time", type=float, default=6.51, help="Measured step time in seconds (default: 6.51)")
    parser.add_argument("--chips", type=int, default=4, help="Total TPU v7 chips in VM (default: 4)")
    parser.add_argument("--peak-tflops-per-chip", type=float, default=2307.0, help="Peak BF16 TFLOPs/chip (default: 2307.0 for TPU v7)")
    
    args = parser.parse_args()
    
    res = compute_llama_grpo_mfu(
        num_params_b=args.params_b,
        seq_len=args.seq_len,
        batch_size=args.batch_size,
        num_generations=args.num_generations,
        step_time_s=args.step_time,
        num_tpu_chips=args.chips,
        peak_tflops_per_chip=args.peak_tflops_per_chip
    )
    
    print("\n" + "=" * 65)
    print("      MaxText GRPO RL Model FLOPs Utilization (MFU) Report")
    print("=" * 65)
    print(f" Model Parameter Count         : {res['num_params_b']:.2f} Billion (LLaMA 3.1-8B)")
    print(f" Hardware Setup                : 1 VM with {args.chips} TPU v7 Chips ({args.chips * 2} Cores total)")
    print(f" Theoretical Peak Throughput   : {res['total_peak_tflops']:.1f} TFLOPs/s ({args.peak_tflops_per_chip:.1f} TFLOPs/chip)")
    print(f" Total Tokens per Step         : {res['total_tokens_per_step']} tokens ({args.batch_size} prompt x {args.num_generations} gens x {args.seq_len} ctx)")
    print(f" Measured Step Duration        : {res['step_time_s']:.2f} s/step")
    print(f" Total FLOPs per Step          : {res['total_tflops_per_step']:.2f} TFLOPs")
    print(f" Achieved Execution Speed      : {res['achieved_tflops_s']:.2f} TFLOPs/s ({res['tflops_per_chip']:.2f} TFLOPs/chip)")
    print("-" * 65)
    print(f" >>> Model FLOPs Utilization  : {res['mfu_percent']:.2f}% <<<")
    print("=" * 65 + "\n")

if __name__ == "__main__":
    main()

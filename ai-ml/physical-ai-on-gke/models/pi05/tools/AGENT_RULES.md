Agent rules for this workspace. Read fully before any run.

WHERE WORK RUNS
1. Run everything in THIS workspace on the GPUs already attached. Never submit a
   separate Anyscale job, never provision new nodes, never set accelerator_type.
2. Before relying on any auto-selected compute, verify GPUs are actually present:
   python -c "import ray; ray.init(address='auto', ignore_reinit_error=True); print(ray.cluster_resources())"
   Derive num_workers from the GPU count printed. Never hardcode a GPU count.

HARDWARE DETECTION (never assume, always branch)
3. Precision: check python -c "import torch; print(torch.cuda.get_device_capability())".
   If capability >= (8, 0): keep the pipeline's native bf16.
   If capability < (8, 0), e.g. T4: replace bf16 with fp16 autocast + GradScaler.
   Print which branch was taken as the first log line of training. Do not hardcode either path.

REUSE, DON'T REBUILD
4. Reuse what exists: the shared venv on /mnt/cluster_storage, cached model weights,
   staged datasets. Before installing or downloading ANYTHING, check whether it's
   already there and print what you found. Only build or download what's missing.
4a. Check the S3 mirror before pulling weights from huggingface.co. Course checkpoints are
   mirrored under s3://anyscale-public-materials-use2/ray_summit_robotics_2026/ so that
   hundreds of concurrent clusters can't throttle HF. List that prefix (and its
   hf-cache/hub/) and use what's there; only fall back to HF for what genuinely isn't
   mirrored.

   SmolVLA is already mirrored. Both lerobot/smolvla_base and its
   HuggingFaceTB/SmolVLM2-500M-Video-Instruct backbone are there in HF-cache layout, so
   pointing HF_HOME at a synced copy resolves both offline:
       export HF_HOME=/checkpoint/physical-ai/mirror/hf-cache
       mkdir -p "$HF_HOME/hub"
       # Sync from persistent mirror:
       cp -r /checkpoint/physical-ai/mirror/hf-cache/hub "$HF_HOME/hub"
   ~2.8 GB. /mnt/cluster_storage is NFS-mounted on every node, so that is ONE sync for the
   whole cluster. Do not re-stage per node. Skip it when
   $HF_HOME/hub/models--lerobot--smolvla_base/refs/main already exists. Pass HF_HOME (and
   HF_HUB_OFFLINE=1) through the Ray runtime_env env_vars so workers resolve from the
   mirror too.
5. Verify the venv is actually in use before proceeding: which python must resolve
   under /mnt/cluster_storage. If it doesn't, fix the environment before any install.
6. If a validated pipeline exists in agent_artifacts, run it IN PLACE. Do not copy it
   (copies break the uv lockfile). Do not regenerate validated code.

RUN IDENTITY AND STATE HYGIENE
7. Every training run gets a fresh RUN_NAME with a timestamp:
   RUN_NAME = f"<job>-{time.strftime('%Y%m%d-%H%M%S')}"
   Print the resolved name and confirm no directory with that name exists before fit().
8. Never partially clean run state. If deleting checkpoints, delete the run's entire
   snapshot directory too. A snapshot pointing at deleted files causes restores that
   crash with FileNotFoundError.
9. If you edit any .py file that a running kernel or Ray worker has already imported,
   restart the kernel or session before trusting any traceback from it. Garbled or
   nonsensical traceback lines are the signature of stale bytecode, not the real error.

FAIL FAST, VERIFY CHEAP BEFORE WAITING ON SLOW
10. After every config step, verify it took effect BEFORE starting anything slow.
    Print the effective value (device, dtype, run name, dataset row count, env vars).
11. Read submit and launch output IN FULL before waiting on the run. If it mentions
    workspace-managed pip/conda/uv dependencies being injected (RAY_RUNTIME_ENV_HOOK),
    STOP and fix that first. Injected deps shadow the verified environment.
12. Validate any data or model fix against ONE real batch before spending a launch cycle.

MEMORY DISCIPLINE (32 GB hosts)
13. Keep image and video data uint8 through Ray Data; widen to float32 or fp16 only on
    the GPU in the collate. Never cast inside a map stage.
14. Cap the Ray Data object store (e.g. 4 GB) and .limit() reads to what the step budget
    consumes: steps * batch_size * num_workers + one map batch per worker of slack.
15. Before training, check host headroom on every node and print the lowest.

COMPLETION CONTRACT
16. Do not hand back until: loss is printing per step, a checkpoint file exists on
    disk, and you have re-loaded that checkpoint and printed its keys as proof.
17. If anything fails: diagnose, fix, rerun. Only stop to ask when the decision
    genuinely requires the human (spending money, deleting shared data, changing
    the S3 mirror). State what you tried and what you'd try next.
18. At the end, print a summary: branch decisions taken (precision, GPU count),
    run name, checkpoint path, final loss, wall-clock time.
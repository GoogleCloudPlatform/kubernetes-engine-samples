# Copyright 2025 Google LLC
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

import datasets
import logging
import logging.config
import glob
import os
import signal
import sys
import torch
import transformers
import random

from accelerate import Accelerator
from datasets import Dataset, load_dataset, load_from_disk
from peft import LoraConfig, PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer
from trl import DataCollatorForCompletionOnlyLM, SFTConfig, SFTTrainer
import torch.distributed as dist


def graceful_shutdown(signal_number, stack_frame):
    signal_name = signal.Signals(signal_number).name

    logger.info(f"Received {signal_name}({signal_number}), shutting down...")
    # TODO: Add logic to handled checkpointing if required
    sys.exit(0)


def formatting_prompts_func(data):
    question = data["question"]
    context = data["context"]
    answer = data["answer"]
    template = "Question: {question}\nContext: {context}\nAnswer: {answer}"
    return {"text": template.format(question=question, context=context, answer=answer)}


def get_current_node_id_and_rank():
    if dist.is_initialized():
        logger.info("Distributed training enabled.")
        logger.info("Calculating node id")
        global_rank = dist.get_rank()  # Get the process's rank
        logger.info(f"global_rank: {global_rank}")
        gpu_per_node = torch.cuda.device_count()
        logger.info(f"gpu_per_node: {gpu_per_node}")
        total_gpus = accelerator.state.num_processes
        logger.info(f"total_gpus: {total_gpus}")
        total_nodes = int(total_gpus / gpu_per_node)
        logger.info(f"total_nodes: {total_nodes}")
        node_id = global_rank // gpu_per_node
    else:
        logger.info("Distributed training enabled.")
        node_id = 0
        global_rank = 0
    logger.info(f"node_id: {node_id}")
    return (node_id, global_rank, gpu_per_node)


if __name__ == "__main__":
    # Configure logging
    logging.config.fileConfig("logging.conf")
    logger = logging.getLogger("finetune")

    if "LOG_LEVEL" in os.environ:
        new_log_level = os.environ["LOG_LEVEL"].upper()
        logger.info(
            f"Log level set to '{new_log_level}' via LOG_LEVEL environment variable"
        )
        logging.getLogger().setLevel(new_log_level)
        logger.setLevel(new_log_level)

    datasets.disable_progress_bar()
    transformers.utils.logging.disable_progress_bar()

    logger.info("Configure signal handlers")
    signal.signal(signal.SIGINT, graceful_shutdown)
    signal.signal(signal.SIGTERM, graceful_shutdown)

    accelerator = Accelerator()

    if "MLFLOW_ENABLE" in os.environ and os.environ["MLFLOW_ENABLE"] == "true":
        import mlflow

        remote_server_uri = os.environ["MLFLOW_TRACKING_URI"]
        mlflow.set_tracking_uri(remote_server_uri)

        experiment_name = os.environ["EXPERIMENT"]
        if accelerator.is_main_process:  # Only the main process sets the experiment
            # Check if the experiment already exists
            experiment = mlflow.get_experiment_by_name(experiment_name)
            if experiment is None:
                # Experiment doesn't exist, create it
                try:
                    experiment_id = mlflow.create_experiment(experiment_name)
                    experiment = mlflow.get_experiment(experiment_id)
                    print(
                        f"Created new experiment: {experiment.name} (ID: {experiment.experiment_id})"
                    )
                except Exception as ex:
                    logger.error(f"Create experiment failed: {ex}")
            else:
                # Experiment already exists, use it
                logger.info(
                    f"Using existing experiment: {experiment.name} (ID: {experiment.experiment_id})"
                )

        # Barrier to ensure all processes wait until the experiment is created
        accelerator.wait_for_everyone()
        experiment = mlflow.get_experiment_by_name(experiment_name)

        # Get the node ID
        node, rank, gpu_per_node = get_current_node_id_and_rank()
        node_id = "node_" + str(node)
        logger.info(f"Training at: {node_id} process: {rank}")
        process_id = "process_" + str(rank)

        # Set MLflow experiment and node ID (within the appropriate run context)
        mlflow.set_experiment(experiment_name)
        mlflow.set_system_metrics_node_id(node_id)

        # Check and create/reuse runs
        # Only one process per node creates a run to capture system metrics
        if (rank % gpu_per_node) == 0:
            existing_run = mlflow.search_runs(
                experiment_ids=[experiment.experiment_id],
                filter_string=f"tags.mlflow.runName = '{process_id}'",
            )
            # No existing run with this name
            if len(existing_run) == 0:
                run = mlflow.start_run(
                    run_name=node_id,
                    experiment_id=experiment.experiment_id,
                )
                has_active_ml_flow_run = True
            else:
                logger.info(f"Run with name '{process_id}' already exists")
                client = mlflow.MlflowClient()
                data = client.get_run(mlflow.active_run().info.run_id).data
                logger.info(f"Active run details: '{data}'")

        # logging of model parameters, metrics, and artifacts
        mlflow.autolog()

    # The instruction dataset to use
    dataset_name = os.environ["DATASET_NAME"]

    # The model that you want to train from the Hugging Face hub
    model_name = os.environ["MODEL_NAME"]

    # Fine-tuned model name
    new_model = os.environ["NEW_MODEL"]

    # The root path of where the fine-tuned model will be saved
    save_model_path = os.environ["MODEL_PATH"]

    # Load tokenizer
    tokenizer = AutoTokenizer.from_pretrained(model_name, trust_remote_code=True)
    tokenizer.pad_token = tokenizer.eos_token
    tokenizer.padding_side = "right"  # Fix weird overflow issue with fp16 training

    EOS_TOKEN = tokenizer.eos_token

    # Set limit to a positive number
    limit = int(os.getenv("DATASET_LIMIT", "5000"))

    training_dataset = load_dataset(dataset_name, split="train")
    if limit != -1:
        training_dataset = training_dataset.shuffle(seed=42).select(range(limit))

    logger.info("Data Formatting Started")
    input_data = training_dataset.map(formatting_prompts_func)
    logger.info("Data Formatting Completed")

    ################################################################################
    # QLoRA parameters
    ################################################################################

    # LoRA attention dimension
    lora_r = int(os.getenv("LORA_R", "8"))

    # Alpha parameter for LoRA scaling
    lora_alpha = int(os.getenv("LORA_ALPHA", "16"))

    # Dropout probability for LoRA layers
    lora_dropout = float(os.getenv("LORA_DROPOUT", "0.1"))

    ################################################################################
    # TrainingArguments parameters
    ################################################################################

    # Output directory where the model predictions and checkpoints will be stored
    # output_dir = "./results"

    # Number of training epochs
    num_train_epochs = int(os.getenv("EPOCHS", "1"))

    # Enable fp16/bf16 training (set bf16 to True with an A100)
    fp16 = False
    bf16 = False

    # Batch size per GPU for training
    per_device_train_batch_size = int(os.getenv("TRAIN_BATCH_SIZE", "1"))

    # Batch size per GPU for evaluation
    per_device_eval_batch_size = 1

    # Number of update steps to accumulate the gradients for
    gradient_accumulation_steps = int(os.getenv("GRADIENT_ACCUMULATION_STEPS", "1"))

    # Enable gradient checkpointing
    gradient_checkpointing = True

    # Maximum gradient normal (gradient clipping)
    max_grad_norm = float(os.getenv("MAX_GRAD_NORM", "0.3"))

    # Initial learning rate (AdamW optimizer)
    learning_rate = float(os.getenv("LEARNING_RATE", "2e-4"))

    # Weight decay to apply to all layers except bias/LayerNorm weights
    weight_decay = float(os.getenv("WEIGHT_DECAY", "0.001"))

    # Optimizer to use
    optim = "paged_adamw_32bit"

    # Learning rate schedule
    lr_scheduler_type = "cosine"

    # Number of training steps (overrides num_train_epochs)
    max_steps = -1

    # Ratio of steps for a linear warmup (from 0 to learning rate)
    warmup_ratio = float(os.getenv("WARMUP_RATIO", "0.03"))

    # Group sequences into batches with same length
    # Saves memory and speeds up training considerably
    group_by_length = True

    # Save strategy: steps, epoch, no
    save_strategy = os.getenv("CHECKPOINT_SAVE_STRATEGY", "steps")

    # Save total limit of checkpoints
    save_total_limit = int(os.getenv("CHECKPOINT_SAVE_TOTAL_LIMIT", "5"))

    # Save checkpoint every X updates steps
    save_steps = int(os.getenv("CHECKPOINT_SAVE_STEPS", "1000"))

    # Log every X updates steps
    logging_steps = 50

    ################################################################################
    # SFT parameters
    ################################################################################

    # Maximum sequence length to use
    max_seq_length = int(os.getenv("MAX_SEQ_LENGTH", "512"))

    # Pack multiple short examples in the same input sequence to increase efficiency
    packing = False

    # Load base model
    logger.info("Loading base model started")
    model = AutoModelForCausalLM.from_pretrained(
        attn_implementation="eager",
        pretrained_model_name_or_path=model_name,
        torch_dtype=torch.bfloat16,
    )
    model.config.use_cache = False
    model.config.pretraining_tp = 1
    logger.info("Loading base model completed")

    logger.info("Configuring fine tuning started")
    # Load LoRA configuration
    peft_config = LoraConfig(
        lora_alpha=lora_alpha,
        lora_dropout=lora_dropout,
        r=lora_r,
        bias="none",
        task_type="CAUSAL_LM",
        target_modules=[
            "q_proj",
            "k_proj",
            "v_proj",
            "o_proj",
            "gate_proj",
            "up_proj",
            "down_proj",
        ],
    )

    # Set training parameters
    training_arguments = SFTConfig(
        bf16=bf16,
        dataset_kwargs={
            "add_special_tokens": False,  # We template with special tokens
            "append_concat_token": False,  # No need to add additional separator token
        },
        dataset_text_field="text",
        disable_tqdm=True,
        fp16=fp16,
        gradient_accumulation_steps=gradient_accumulation_steps,
        gradient_checkpointing=gradient_checkpointing,
        gradient_checkpointing_kwargs={"use_reentrant": False},
        group_by_length=group_by_length,
        log_on_each_node=False,
        logging_steps=logging_steps,
        learning_rate=learning_rate,
        lr_scheduler_type=lr_scheduler_type,
        max_grad_norm=max_grad_norm,
        max_seq_length=max_seq_length,
        max_steps=max_steps,
        num_train_epochs=num_train_epochs,
        optim=optim,
        output_dir=save_model_path,
        packing=packing,
        per_device_train_batch_size=per_device_train_batch_size,
        save_strategy=save_strategy,
        save_steps=save_steps,
        save_total_limit=save_total_limit,
        warmup_ratio=warmup_ratio,
        weight_decay=weight_decay,
    )
    logger.info("Configuring fine tuning completed")

    logger.info("Creating trainer started")
    trainer = SFTTrainer(
        args=training_arguments,
        model=model,
        peft_config=peft_config,
        tokenizer=tokenizer,
        train_dataset=input_data,
    )
    logger.info("Creating trainer completed")

    logger.info("Fine tuning started")
    # Check for existing checkpoints
    checkpoints_present = glob.glob(f"{save_model_path}/checkpoint-*") != []
    trainer.train(resume_from_checkpoint=checkpoints_present)
    logger.info("Fine tuning completed")

    if "MLFLOW_ENABLE" in os.environ and os.environ["MLFLOW_ENABLE"] == "true":
        if accelerator.is_main_process:  # register the model only at main process
            mv = mlflow.register_model(
                model_uri=f"gs://{training_data_bucket}/{save_model_path}",
                name=new_model,
            )
            logger.info(f"Name: {mv.name}")
            logger.info(f"Version: {mv.version}")

    logger.info("Saving new model started")
    trainer.model.save_pretrained(new_model)
    logger.info("Saving new model completed")

    logger.info("Merging the new model with base model started")
    # Reload model in FP16 and merge it with LoRA weights
    base_model = AutoModelForCausalLM.from_pretrained(
        low_cpu_mem_usage=True,
        pretrained_model_name_or_path=model_name,
        return_dict=True,
        torch_dtype=torch.bfloat16,
    )
    model = PeftModel.from_pretrained(
        model=base_model,
        model_id=new_model,
    )
    model = model.merge_and_unload()
    logger.info("Merging the new model with base model completed")

    logger.info("Accelerate unwrap model started")
    unwrapped_model = accelerator.unwrap_model(model)
    logger.info("Accelerate unwrap model completed")

    logger.info("Save unwrapped model started")
    unwrapped_model.save_pretrained(
        is_main_process=accelerator.is_main_process,
        save_directory=save_model_path,
        save_function=accelerator.save,
    )
    logger.info("Save unwrapped model completed")

    logger.info("Save new tokenizer started")
    if accelerator.is_main_process:
        tokenizer.save_pretrained(save_model_path)
    logger.info("Save new tokenizer completed")

    # Barrier to ensure all processes wait until 'unwrapped model save' is completed
    accelerator.wait_for_everyone()

    logger.info("Script completed")

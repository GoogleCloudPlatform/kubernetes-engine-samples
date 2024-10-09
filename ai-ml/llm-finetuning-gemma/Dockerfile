# Copyright 2024 Google LLC
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

# [START gke_aiml_llm_finetune_gemma_single_node_docker]
FROM nvidia/cuda:12.6.1-runtime-ubuntu22.04

RUN apt-get update && \
    apt-get -y --no-install-recommends install python3-dev gcc python3-pip git && \
    rm -rf /var/lib/apt/lists/*

RUN pip3 install --no-cache-dir \
    accelerate==0.30.1 bitsandbytes==0.43.1 \
    datasets==2.19.1 transformers==4.41.0 \
    peft==0.11.1 trl==0.8.6 torch==2.3.0

COPY finetune.py /finetune.py

ENV PYTHONUNBUFFERED 1

CMD python3 /finetune.py --device cuda
# [END gke_aiml_llm_finetune_gemma_single_node_docker]

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

# DEVELOPMENT DEVELOPMENT DEVELOPMENT DEVELOPMENT DEVELOPMENT DEVELOPMENT
# DEVELOPMENT DEVELOPMENT DEVELOPMENT DEVELOPMENT DEVELOPMENT DEVELOPMENT
# DEVELOPMENT DEVELOPMENT DEVELOPMENT DEVELOPMENT DEVELOPMENT DEVELOPMENT
FROM pytorch/pytorch:2.5.1-cuda12.1-cudnn9-devel AS devel

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN apt-get update && \
    apt-get install -y \
    git && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt /workspace/
RUN pip wheel --no-cache-dir --no-deps --wheel-dir /workspace/wheels -r /workspace/requirements.txt





# FINAL FINAL FINAL FINAL FINAL FINAL FINAL FINAL FINAL FINAL FINAL FINAL
# FINAL FINAL FINAL FINAL FINAL FINAL FINAL FINAL FINAL FINAL FINAL FINAL
# FINAL FINAL FINAL FINAL FINAL FINAL FINAL FINAL FINAL FINAL FINAL FINAL
FROM pytorch/pytorch:2.5.1-cuda12.1-cudnn9-runtime

RUN apt-get update && \
    apt-get install -y \
    git && \
    rm -rf /var/lib/apt/lists/*

COPY --from=devel /workspace/wheels /workspace/wheels
COPY requirements.txt /workspace/
RUN pip install --no-cache /workspace/wheels/*

COPY fine_tune.py fsdp_config.yaml logging.conf /workspace/

# Copyright 2023 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

ARG BASE_IMAGE=pytorch/torchserve:0.12.0-cpu

FROM alpine/git

ARG MODEL_NAME=t5-small
ARG MODEL_REPO=https://huggingface.co/${MODEL_NAME}
ENV MODEL_NAME=${MODEL_NAME}
ENV MODEL_VERSION=${MODEL_VERSION}

RUN git clone "${MODEL_REPO}" /model

FROM ${BASE_IMAGE}

ARG MODEL_NAME=t5-small
ARG MODEL_VERSION=1.0
ENV MODEL_NAME=${MODEL_NAME}
ENV MODEL_VERSION=${MODEL_VERSION}

COPY --from=0 /model/. /home/model-server/
COPY handler.py \
     model.py \
     requirements.txt \
     setup_config.json /home/model-server/

RUN  torch-model-archiver \
     --model-name="${MODEL_NAME}" \
     --version="${MODEL_VERSION}" \
     --model-file="model.py" \
     --serialized-file="pytorch_model.bin" \
     --handler="handler.py" \
     --extra-files="config.json,spiece.model,tokenizer.json,setup_config.json" \
     --runtime="python" \
     --export-path="model-store" \
     --requirements-file="requirements.txt"

FROM ${BASE_IMAGE}

ENV PATH /home/model-server/.local/bin:$PATH
ENV TS_CONFIG_FILE /home/model-server/config.properties
# CPU inference will throw a warning cuda warning (not error)
# Could not load dynamic library 'libnvinfer_plugin.so.7'
# This is expected behaviour. see: https://stackoverflow.com/a/61137388
ENV TF_CPP_MIN_LOG_LEVEL 2

COPY --from=1 /home/model-server/model-store/ /home/model-server/model-store
COPY config.properties /home/model-server/

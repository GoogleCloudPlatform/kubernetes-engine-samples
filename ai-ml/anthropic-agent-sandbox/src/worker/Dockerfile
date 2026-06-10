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

FROM debian:12-slim

ARG ANT_VERSION=1.9.1
ARG NODE_VERSION=22

RUN apt-get update && apt-get install -y --no-install-recommends \
      bash \
      ca-certificates \
      curl \
      tar \
      unzip \
      python3 \
    && curl -fsSL https://deb.nodesource.com/setup_${NODE_VERSION}.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

ARG TARGETARCH
RUN ARCH=$([ "${TARGETARCH:-amd64}" = "arm64" ] && echo arm64 || echo amd64) \
    && curl -fsSL "https://github.com/anthropics/anthropic-cli/releases/download/v${ANT_VERSION}/ant_${ANT_VERSION}_linux_${ARCH}.tar.gz" \
       | tar -xz -C /usr/local/bin ant \
    && ant --version

RUN useradd --create-home --uid 1000 worker \
    && mkdir -p /workspace /mnt/session /mnt/gcs \
    && chown -R worker:worker /workspace /mnt/session /mnt/gcs

COPY --chown=worker:worker entrypoint.py /usr/local/bin/entrypoint.py

USER worker
WORKDIR /workspace

ENTRYPOINT ["python3", "/usr/local/bin/entrypoint.py"]

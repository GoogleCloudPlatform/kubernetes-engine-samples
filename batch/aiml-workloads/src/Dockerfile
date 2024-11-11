# Copyright 2022 Google LLC
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

# [START gke_batch_aiml_workload_dockerfile]
FROM python:3.13-slim
COPY ./requirements.txt /requirements.txt
RUN pip install -r requirements.txt

COPY ./worker.py /worker.py
COPY ./rediswq.py /rediswq.py
COPY ./model_training.py /model_training.py

CMD  python worker.py
# [END gke_batch_aiml_workload_dockerfile]

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

# [START gke_ai_ml_gke_ray_tpu_get_started_serve_predict]
"""Send a prediction to the Qwen3-4B-Instruct-2507 Ray Serve endpoint.

Ray Serve exposes an OpenAI-compatible API, so you can use the openai client.
First port-forward the serve service:

    kubectl port-forward svc/qwen3-serve-serve-svc 8000:8000

Then:

    python predict.py "What is a TPU slice?"

Qwen3-4B-Instruct-2507 is a text-only model, so this client sends text prompts.
Install the client with:  pip install openai
"""
import argparse
import os

from openai import OpenAI

# Match the model_id served by serve_qwen3_tpu.py (overridable via MODEL_ID).
MODEL_ID = os.environ.get("MODEL_ID", "Qwen/Qwen3-4B-Instruct-2507")


def main() -> None:
    """Sends one prompt to the serve endpoint and prints the reply."""
    parser = argparse.ArgumentParser()
    parser.add_argument("prompt", help="Text prompt to send to the model")
    parser.add_argument("--base-url", default="http://localhost:8000/v1")
    parser.add_argument("--max-tokens", type=int, default=512)
    args = parser.parse_args()

    # Ray Serve doesn't require a real key. Any non-empty string works.
    client = OpenAI(base_url=args.base_url, api_key="not-needed")

    resp = client.chat.completions.create(
        model=MODEL_ID,
        messages=[{"role": "user", "content": args.prompt}],
        max_tokens=args.max_tokens,
    )
    print(resp.choices[0].message.content)


if __name__ == "__main__":
    main()
# [END gke_ai_ml_gke_ray_tpu_get_started_serve_predict]

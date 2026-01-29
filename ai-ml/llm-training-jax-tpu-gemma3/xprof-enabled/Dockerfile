FROM us-docker.pkg.dev/cloud-tpu-images/jax-ai-image/tpu:jax0.7.2-rev1
RUN apt-get update && apt-get install -y wget && rm -rf /var/lib/apt/lists/*

RUN pip install --upgrade pip
RUN pip install gemma grain equinox
RUN pip install xprof

WORKDIR /app

# Copy your training script into the container
COPY Gemma3LLMTrain.py .

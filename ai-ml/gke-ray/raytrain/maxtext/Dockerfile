# [START gke_ai_ml_gke_ray_ray_train_maxtext_dockerfile]
# Start from a Ray base image which includes JaxTrainer API.
# Maxtext with TPU requires Python 3.12.
FROM rayproject/ray:2.49.1-py312

USER root
RUN groupadd -r ray 2>/dev/null || true && usermod -g ray ray

RUN sudo apt-get update -y \
  && sudo apt-get install --no-install-recommends -y git \
  && sudo rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Clone the Maxtext repo and build from source, installing TPU dependencies.
RUN git clone https://github.com/AI-Hypercomputer/maxtext.git

RUN pip install --no-cache-dir uv

RUN cd maxtext && \
    uv pip install --no-cache --system -e .[tpu] --resolution=lowest && \
    install_maxtext_github_deps

# Copy the Ray Maxtext trainer to run on the remote container.
COPY maxtext_ray_trainer.py .

RUN chown -R ray:ray .
ENV PYTHONPATH=/app/maxtext/src:/app/maxtext:/app
USER ray
# [END gke_ai_ml_gke_ray_ray_train_maxtext_dockerfile]
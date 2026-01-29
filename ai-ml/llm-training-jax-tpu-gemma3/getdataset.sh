#!/bin/bash

wget https://huggingface.co/datasets/roneneldan/TinyStories/resolve/main/TinyStories-train.txt?download=true -O TinyStories-train.txt

export GCS_BUCKET_NAME=<BUCKET_NAME>
gcloud storage buckets create gs://${GCS_BUCKET_NAME} \
  --location=us-east5 \
  --enable-hierarchical-namespace \
  --uniform-bucket-level-access

gcloud storage cp TinyStories-train.txt gs://${GCS_BUCKET_NAME}


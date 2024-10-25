FROM nvcr.io/nvidia/tensorflow:22.12-tf2-py3

# Install the latest jax
RUN pip install --upgrade pip
RUN pip install jax[cuda]==0.4.2 -f https://storage.googleapis.com/jax-releases/jax_cuda_releases.html

WORKDIR /scripts
ADD train.py /scripts
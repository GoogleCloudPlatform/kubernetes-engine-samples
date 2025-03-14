FROM python:3.10-slim

RUN pip install --no-cache-dir --upgrade pip

RUN pip install --no-cache-dir --upgrade "jax[cuda12_pip]" -f https://storage.googleapis.com/jax-releases/jax_cuda_releases.html

ENV LD_LIBRARY_PATH=/usr/local/nvidia/lib64

WORKDIR /workspace/

ADD jax_pingpong_tcpx.py .
ADD start_jax_pingpong_tcpx.sh .

ENTRYPOINT ["bash", "start_jax_pingpong_tcpx.sh"]
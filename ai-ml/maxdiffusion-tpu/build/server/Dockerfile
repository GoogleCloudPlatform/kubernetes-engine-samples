
FROM python:3.11-slim
WORKDIR /app
RUN apt-get -y update
RUN apt-get -y install git
COPY requirements.txt ./
RUN python -m pip install --upgrade pip
RUN pip install -U "jax[tpu]" -f https://storage.googleapis.com/cloud-tpu-tpuvm-artifacts/wheels/libtpu-nightly/libtpu_nightly-0.1.dev20240508-py3-none-any.whl #https://storage.googleapis.com/jax-releases/libtpu_releases.html
RUN pip install -r requirements.txt
RUN pip install git+https://github.com/google/maxdiffusion.git
COPY main.py ./
EXPOSE 8000
ENTRYPOINT ["python", "main.py"]
FROM python:3.12-slim-bookworm

ENV POSTGRES_HOST gke-pg-cluster-rw.pg-ns
ENV DATABASE_NAME app
ENV COLLECTION_NAME training-docs
RUN apt update && \
    apt install -y --no-install-recommends gcc libc6-dev && \
    rm -rf /var/lib/apt/lists/*
RUN mkdir -p /documents
WORKDIR /app
COPY requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN chmod 765 endpoint.py
EXPOSE 5001

CMD ["/app/embedding-job.py"]
ENTRYPOINT ["python"]

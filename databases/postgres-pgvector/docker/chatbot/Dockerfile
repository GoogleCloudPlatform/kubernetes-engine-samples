FROM python:3.13-slim-bookworm

ENV POSTGRES_HOST gke-pg-cluster-rw.pg-ns
ENV DATABASE_NAME app
ENV COLLECTION_NAME training-docs
RUN apt update && \
    apt install -y --no-install-recommends gcc libc6-dev && \
    rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

CMD ["run","/app/chat.py"]
ENTRYPOINT ["streamlit"]


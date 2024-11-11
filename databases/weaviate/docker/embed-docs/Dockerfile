FROM python:3.13-slim-bookworm

ENV WEAVIATE_ENDPOINT weaviate.weaviate
ENV WEAVIATE_GRPC_ENDPOINT weaviate-grpc.weaviate

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

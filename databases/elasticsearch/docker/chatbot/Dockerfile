FROM python:3.12-slim-bookworm

ENV ES_URL https://elasticsearch-ha-es-http:9200
ENV INDEX_NAME training-docs
RUN apt update && \
    apt install -y --no-install-recommends gcc libc6-dev && \
    rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

CMD ["run","/app/chat.py"]
ENTRYPOINT ["streamlit"]


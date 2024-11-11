FROM python:3.12-slim-bookworm

ENV QDRANT_URL http://qdrant-database:6333
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


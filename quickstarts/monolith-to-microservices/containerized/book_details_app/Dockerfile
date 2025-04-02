# Dockerfile for book_details_app
FROM python:3.9-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY book_details_app.py .
COPY data/ ./data/

CMD ["python", "book_details_app.py"]
# Dockerfile for book_reviews_app
FROM python:3.14-alpine

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY book_reviews_app.py .
COPY data/ ./data/

CMD ["python", "book_reviews_app.py"]
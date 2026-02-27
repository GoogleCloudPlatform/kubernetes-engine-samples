# Dockerfile for home_app
FROM python:3.14-alpine

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY home_app.py .
COPY templates/ ./templates/
COPY static/ ./static/


CMD ["python", "home_app.py"]
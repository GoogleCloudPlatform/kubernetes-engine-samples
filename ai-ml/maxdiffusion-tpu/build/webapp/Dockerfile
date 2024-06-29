
FROM python:3.10-slim
WORKDIR /app
COPY requirements.txt ./
RUN python -m pip install --upgrade pip
RUN pip install -r requirements.txt
COPY app.py ./
CMD [ "python", "-m" , "flask", "run", "--host=0.0.0.0"]

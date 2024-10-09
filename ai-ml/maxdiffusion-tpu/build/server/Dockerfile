
FROM python:3.12-slim
WORKDIR /app
RUN apt-get -y update
RUN apt-get -y install git
COPY requirements.txt ./
RUN python -m pip install --upgrade pip
RUN pip install -r requirements.txt
RUN pip install git+https://github.com/google/maxdiffusion.git
COPY main.py ./
EXPOSE 8000
ENTRYPOINT ["python", "main.py"]

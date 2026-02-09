FROM python:3.13.11-slim

#MAINTAINER Alex Mattson "alex.mattson@gmail.com"

RUN apt-get update && apt-get install -y --no-install-recommends \
  wget && \
  apt-get clean && \
  rm -rf /var/lib/apt/lists/* && \
  wget -O /bin/curl https://github.com/moparisthebest/static-curl/releases/download/v8.17.0/curl-amd64 && \ 
  chmod +x /bin/curl
COPY ./requirements.txt /app/requirements.txt

WORKDIR /app

RUN pip install -r requirements.txt

COPY . /app

#RUN addgroup -S appuser && adduser -S -G appuser appuser # commented out when switching to `slim` from `alpine`
RUN addgroup --system appuser && adduser --system appuser --ingroup appuser
USER appuser

ENTRYPOINT [ "python" ]

CMD [ "app.py" ]

ARG BUILD_FROM=ghcr.io/home-assistant/amd64-base:latest
FROM $BUILD_FROM

RUN apk add --no-cache \
    python3 \
    py3-pip

WORKDIR /app

COPY requirements.txt .
RUN python3 -m pip install --no-cache-dir --break-system-packages -r requirements.txt

COPY app/ ./app/
COPY shared/ ./shared/
COPY run.sh /

RUN chmod a+x /run.sh

CMD [ "/run.sh" ]

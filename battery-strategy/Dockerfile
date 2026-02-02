ARG BUILD_FROM=ghcr.io/home-assistant/amd64-base:latest
FROM $BUILD_FROM

# Install requirements for add-on
COPY requirements.txt /tmp/
RUN pip install --no-cache-dir --break-system-packages -r /tmp/requirements.txt

WORKDIR /app

# Copy shared modules first (synced via sync_shared.py)
COPY shared /app/shared

# Copy add-on code
COPY app /app/app
COPY run.sh /run.sh

RUN chmod a+x /run.sh

CMD [ "/run.sh" ]

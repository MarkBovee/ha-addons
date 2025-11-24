ARG BUILD_FROM=ghcr.io/home-assistant/amd64-base:latest
FROM $BUILD_FROM

# Install Python 3 and pip
RUN apk add --no-cache python3 py3-pip

# Set working directory
WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN python3 -m pip install --no-cache-dir --break-system-packages -r requirements.txt

# Copy application code
COPY app/ ./app/
COPY run.sh /

# Make run.sh executable
RUN chmod a+x /run.sh

# Set entry point
CMD [ "/run.sh" ]


ARG BUILD_FROM=ghcr.io/home-assistant/amd64-base:latest
FROM $BUILD_FROM

# Install Python and dependencies
RUN apk add --no-cache \
    python3 \
    py3-pip

# Set working directory
WORKDIR /app

# Copy requirements and install Python packages
COPY requirements.txt .
RUN python3 -m pip install --no-cache-dir --break-system-packages -r requirements.txt

# Copy application files
COPY app/ ./app/
COPY run.sh /

# Make run script executable
RUN chmod a+x /run.sh

# Run the add-on
CMD [ "/run.sh" ]

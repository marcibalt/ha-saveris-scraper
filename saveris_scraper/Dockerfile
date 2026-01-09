FROM python:3.11-slim

# Install Chromium + ChromeDriver (Debian/Ubuntu packages)
RUN apt-get update && apt-get install -y --no-install-recommends \
    chromium \
    chromium-driver \
    fonts-liberation \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Python deps
RUN pip install --no-cache-dir selenium flask

# Debian paths
ENV CHROME_BIN=/usr/bin/chromium
ENV CHROMEDRIVER_BIN=/usr/bin/chromedriver

# Software rendering (safe in containers)
ENV LIBGL_ALWAYS_SOFTWARE=1

COPY run.sh /run.sh
COPY app.py /app.py
RUN chmod +x /run.sh

CMD ["/run.sh"]

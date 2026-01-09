FROM python:3.11-alpine

RUN apk add --no-cache \
    chromium \
    chromium-chromedriver \
    ca-certificates \
    nss \
    freetype \
    harfbuzz \
    ttf-freefont \
    udev \
    dbus \
    mesa-gl \
    libstdc++ \
    libgcc

RUN pip install --no-cache-dir selenium flask
ENV LIBGL_ALWAYS_SOFTWARE=1
ENV CHROME_BIN=/usr/bin/chromium-browser
ENV CHROMEDRIVER_BIN=/usr/bin/chromedriver

COPY run.sh /run.sh
COPY app.py /app.py
RUN chmod +x /run.sh

CMD [ "/run.sh" ]

FROM python:3.11-alpine

RUN apk add --no-cache \
    chromium \
    chromium-chromedriver \
    nss \
    freetype \
    harfbuzz \
    ttf-freefont

RUN pip install --no-cache-dir selenium flask

ENV CHROME_BIN=/usr/bin/chromium-browser
ENV CHROMEDRIVER_BIN=/usr/bin/chromedriver

COPY run.sh /run.sh
COPY app.py /app.py
RUN chmod +x /run.sh

CMD [ "/run.sh" ]

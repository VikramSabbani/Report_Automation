
FROM python:3.12-slim-bookworm

ENV PYTHONUNBUFFERED=1
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    nodejs \
    npm \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY backend/package.json ./backend/package.json
RUN cd /app/backend && npm install --omit=dev

COPY python-automation/requirements.txt ./python-automation/requirements.txt
RUN pip install --no-cache-dir -r /app/python-automation/requirements.txt \
    && playwright install --with-deps chromium

COPY backend/ ./backend/
COPY python-automation/ ./python-automation/

WORKDIR /app/backend

ENV PORT=10000
EXPOSE 10000

CMD ["node", "server.js"]

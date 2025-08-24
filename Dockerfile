# syntax=docker/dockerfile:1
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# System deps for Playwright and general build tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl wget gnupg \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps first (leverage layer cache)
COPY requirements.txt ./
RUN pip install --upgrade pip setuptools wheel \
    && pip install --only-binary=:all: -r requirements.txt

# Install OS dependencies required by Chromium on Debian (avoid install-deps name mismatches)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libnss3 libatk-bridge2.0-0 libgtk-3-0 libx11-xcb1 libxcb1 libxcomposite1 \
    libxdamage1 libxfixes3 libxrandr2 libgbm1 libasound2 libxshmfence1 libdrm2 \
    libxext6 libxkbcommon0 libpango-1.0-0 libcairo2 libatspi2.0-0 libx11-6 \
    libxss1 libxtst6 libxrender1 libxi6 fonts-liberation \
    && rm -rf /var/lib/apt/lists/* \
    && python -m playwright install chromium

# Copy app
COPY . .

EXPOSE 10000

CMD ["python", "main.py"]
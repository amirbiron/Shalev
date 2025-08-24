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

# Install browser and OS deps for Playwright (chromium)
RUN python -m playwright install-deps chromium \
    && python -m playwright install chromium

# Copy app
COPY . .

EXPOSE 10000

CMD ["python", "main.py"]
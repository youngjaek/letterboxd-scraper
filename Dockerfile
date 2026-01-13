FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && apt-get install -y build-essential libpq-dev && rm -rf /var/lib/apt/lists/*
RUN pip install --upgrade pip

COPY pyproject.toml ./
COPY src ./src
COPY config ./config
COPY db ./db

RUN pip install --no-cache-dir -e .

COPY . .

CMD ["python", "-m", "letterboxd_scraper.cli", "--help"]

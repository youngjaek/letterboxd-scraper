FROM python:3.11-slim

WORKDIR /app
COPY pyproject.toml .
RUN pip install --upgrade pip && pip install --no-cache-dir poetry
RUN poetry config virtualenvs.create false
RUN poetry install --only main
COPY . .
CMD ["python", "-m", "letterboxd_scraper.cli", "--help"]

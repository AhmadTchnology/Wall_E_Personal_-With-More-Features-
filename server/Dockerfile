FROM python:3.12-slim AS base

WORKDIR /app

# Install system deps for asyncpg
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc libpq-dev && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 7125

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "7125"]

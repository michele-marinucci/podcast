FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Episode artifacts land in /app/output — mount a volume there in production
# so episodes survive restarts (or publish to R2/S3 via src/publish.py).
EXPOSE 8000
CMD ["uvicorn", "src.webapp:app", "--host", "0.0.0.0", "--port", "8000"]

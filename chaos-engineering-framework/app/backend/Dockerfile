# Build context is ./app  ->  docker build -f app/backend/Dockerfile app
FROM python:3.11-slim
WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY common/telemetry.py .
COPY backend/app.py .
EXPOSE 8080
CMD ["gunicorn", "-b", "0.0.0.0:8080", "-w", "1", "--threads", "32", "app:app"]

# Build context is ./aiops  ->  docker build -t chaos-lab/aiops:1.0 aiops
FROM python:3.11-slim
WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY analyze.py .

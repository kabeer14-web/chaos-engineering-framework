# Build context is ./app  ->  docker build -f app/loadgen/Dockerfile app
FROM python:3.11-slim
WORKDIR /srv
RUN pip install --no-cache-dir requests==2.32.3 prometheus-client==0.20.0
COPY loadgen/loadgen.py .
EXPOSE 9100
CMD ["python", "loadgen.py"]

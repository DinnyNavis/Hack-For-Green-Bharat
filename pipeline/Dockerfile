FROM python:3.11-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y gcc g++ && rm -rf /var/lib/apt/lists/*
COPY pipeline/requirements.txt /app/requirements.txt
RUN pip install --upgrade pip && pip install --no-cache-dir -r requirements.txt
COPY pipeline/ /app/pipeline/
COPY data/ /app/data/
RUN mkdir -p /app/output
ENV PYTHONPATH=/app/pipeline
CMD ["python", "/app/pipeline/main.py"]

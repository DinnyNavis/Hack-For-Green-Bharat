FROM python:3.11-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1
COPY requirements.txt .
RUN pip install --upgrade pip && pip install --no-cache-dir -r requirements.txt
COPY notifier.py .
CMD ["python", "notifier.py"]

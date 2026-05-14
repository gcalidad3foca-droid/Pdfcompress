FROM python:3.11-slim
 
RUN apt-get update && apt-get install -y \
    ghostscript \
    libqpdf-dev \
    qpdf \
    && rm -rf /var/lib/apt/lists/*
 
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY servidor_gs.py .
 
EXPOSE 10000
CMD ["gunicorn", "--bind", "0.0.0.0:10000", "--timeout", "300", "--workers", "2", "servidor_gs:app"]

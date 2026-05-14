FROM python:3.11-slim

# Instalar Ghostscript (binario real)
RUN apt-get update && apt-get install -y ghostscript && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY servidor_gs.py .

EXPOSE 10000

CMD ["gunicorn", "--bind", "0.0.0.0:10000", "servidor_gs:app"]

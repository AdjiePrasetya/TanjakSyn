FROM python:3.10-slim

# Set env supaya apt tidak interaktif
ENV DEBIAN_FRONTEND=noninteractive

# 🔥 INSTALL SYSTEM LIB - lebih efisien
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender1 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Fix: init_db dipanggil saat startup
RUN python -c "from database.db import init_db; init_db()" || true

EXPOSE 5000
CMD ["gunicorn", "app:app", "--bind", "0.0.0.0:5000", "--workers", "2", "--timeout", "120"]
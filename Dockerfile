FROM python:3.10-slim

# Install system dependencies (INI YANG FIX ERROR)
RUN apt-get update && apt-get install -y \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy project
COPY . .

# Install python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Jalankan app
CMD ["gunicorn", "app:app", "--bind", "0.0.0.0:8080"]
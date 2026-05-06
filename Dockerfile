# Gunakan base image Python
FROM python:3.10

# Set working directory
WORKDIR /app

# Copy semua file ke dalam container
COPY . /app

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Buka port 7860
EXPOSE 7860

# Jalankan aplikasi
CMD ["python", "app.py"]
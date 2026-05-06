FROM python:3.10-slim

# Install dependency system (WAJIB buat mediapipe & cv2)
RUN apt-get update && apt-get install -y \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY . .

RUN pip install --no-cache-dir -r requirements.txt

# Gunakan port 8080 (standar cloud)
EXPOSE 8080

CMD ["gunicorn", "app:app", "--bind", "0.0.0.0:8080"]
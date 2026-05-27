# Menggunakan image dasar Python 3.10-slim yang ringan dan efisien untuk container
FROM python:3.10-slim

# Menetapkan environment variable agar instalasi paket debian (apt) berjalan secara non-interaktif
# Ini mencegah proses build terhenti karena menunggu masukan/konfirmasi dari pengguna
ENV DEBIAN_FRONTEND=noninteractive

# ── INSTALASI PERPUSTAKAAN SISTEM (SYSTEM LIBRARIES) ───────────────────────────────────
# Langkah ini sangat krusial karena pustaka seperti OpenCV, MediaPipe, dan ONNX (Rembg)
# bergantung pada pustaka C/C++ tingkat sistem untuk komputasi grafis dan akselerasi AI.
# - libgl1: Diperlukan oleh OpenCV untuk fungsi OpenGL / rendering grafis.
# - libglib2.0-0: Diperlukan oleh OpenCV untuk pemrosesan event dan thread tingkat rendah.
# - libsm6, libxext6, libxrender1: Pustaka pendukung grafis X11 untuk manipulasi citra.
# - libgomp1: Diperlukan untuk komputasi paralel OpenMP (sangat penting untuk efisiensi akselerasi AI).
# - libegl1: Diperlukan oleh MediaPipe untuk rendering grafis offscreen via EGL.
# Setelah instalasi, dilakukan pembersihan cache apt untuk memperkecil ukuran image Docker.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender1 \
    libgomp1 \
    libegl1 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Menentukan direktori kerja utama di dalam container
WORKDIR /app

# Menyalin file daftar dependensi Python ke dalam direktori kerja container
COPY requirements.txt .

# Menginstal semua dependensi Python yang tercantum di requirements.txt tanpa menyimpan cache pip
# untuk meminimalkan konsumsi ruang disk pada image akhir
RUN pip install --no-cache-dir -r requirements.txt

# Menyalin seluruh kode sumber proyek dari host ke dalam direktori kerja container
COPY . .

# Melakukan inisialisasi basis data SQLite saat build image berlangsung.
# Memanggil fungsi `init_db` dari modul `database.db` untuk membuat tabel dan memasukkan seed data awal.
# Menggunakan operator fallback `|| true` untuk memastikan build tidak gagal jika terjadi kendala minor pada inisialisasi awal.
RUN python -c "from database.db import init_db; init_db()" || true

# Menginformasikan bahwa container akan mendengarkan koneksi pada port 5000
EXPOSE 5000

# Menentukan perintah default untuk menjalankan aplikasi menggunakan server produksi Gunicorn.
# Konfigurasi:
# - app:app -> merujuk pada objek Flask `app` di dalam berkas `app.py`
# - --bind 0.0.0.0:5000 -> melayani permintaan pada semua antarmuka jaringan di port 5000
# - --workers 2 -> menggunakan 2 pekerja worker untuk menangani request secara paralel
# - --timeout 120 -> menetapkan batas waktu request maksimum 120 detik (berguna untuk pemrosesan AI try-on yang memakan waktu)
CMD ["gunicorn", "app:app", "--bind", "0.0.0.0:5000", "--workers", "2", "--timeout", "120"]
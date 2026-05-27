# TanjakSyn v2 — AI Cultural Heritage Platform
## Full Stack: Flask + SQLite + MediaPipe + Responsive Web

---

## 📁 STRUKTUR FOLDER LENGKAP

```
tanjaksyn2/
│
├── app.py                        # 🚀 Backend Flask utama
├── requirements.txt              # 📦 Dependensi Python
├── README.md                     # 📖 Dokumentasi ini
├── .env                          # 🔑 Konfigurasi kredensial admin
│
├── backend/
│   ├── __init__.py
│   └── ai_processor.py           # 🧠 AI MediaPipe (deteksi & pasang tanjak)
│
├── database/
│   ├── __init__.py
│   ├── db.py                     # 💾 SQLite helper (CRUD semua tabel)
│   └── tanjaksyn.db              # 🗃️ Auto-created saat pertama dijalankan
│
├── frontend/
│   ├── index.html                # 🌐 UI Client Utama (Try-On & Galeri)
│   ├── admin.html                # 👑 UI Panel Admin CRUD
│   └── assets/
│       └── logo.png              # 🖼️ Logo TanjakSyn
│
├── tanjak_assets/                # 🎩 Aset PNG tanjak transparan
│   ├── tanjak_lipatan.png
│   ├── tanjak_dondang.png
│   └── tanjak_nobat.png
│
├── uploads/                      # 📁 Auto-created (foto upload try-on)
└── outputs/                      # 📁 Auto-created (hasil try-on)
```

---

## 🌟 FITUR UTAMA PROYEK

1. **AI Virtual Try-On Tanjak secara Real-Time**:
   Mencoba tanjak secara langsung melalui kamera web atau unggah foto. Memanfaatkan **MediaPipe Face Mesh** untuk mendeteksi posisi kepala secara presisi (468 landmarks), menghitung skala, orientasi, serta melakukan overlay visual tanjak dengan mulus.
2. **Katalog Warisan Budaya Interaktif**:
   Daftar komprehensif jenis tanjak Melayu yang dilengkapi detail asal-usul, fungsi penggunaan adat, harga, serta cerita filosofi budayanya.
3. **Pemberdayaan Pengrajin Lokal (Sistem Kemitraan UMKM)**:
   Menghubungkan pembeli langsung dengan pengrajin (artisan) pembuat tanjak. Menyediakan tombol kontak langsung via WhatsApp, peta lokasi, rating, dan data penjualan.
4. **Galeri Publik Karya Pengguna**:
   Pengguna dapat membagikan hasil foto try-on terbaik mereka ke galeri bersama yang dapat dilihat dan disukai (like) oleh pengunjung lain.
5. **Dashboard Panel Admin Terproteksi (CRUD)**:
   Halaman khusus `/admin` untuk mengelola katalog produk (tambah produk dengan upload gambar, edit spesifikasi scaling try-on, soft-delete) serta database mitra UMKM secara mudah dan aman dengan otentikasi Flask Session.
6. **Desain Visual Heritage & Responsif**:
   Tampilan antarmuka mewah dengan palet warna tradisional (Maroon, Gold, Cream) yang dioptimalkan secara mobile-first untuk pengalaman pengguna terbaik di semua ukuran layar.

---

## ⚡ RUNTUTAN MENJALANKAN

### LANGKAH 1 — Persiapan Python

```bash
# Masuk ke folder project
cd tanjaksyn2

# Buat virtual environment
python -m venv venv

# Aktifkan virtual environment:
source venv/bin/activate        # macOS / Linux
venv\Scripts\activate           # Windows (cmd)
.\venv\Scripts\Activate.ps1     # Windows (PowerShell)
```

### LANGKAH 2 — Install Semua Dependensi

```bash
pip install -r requirements.txt
```

> ⏳ Pertama kali memakan waktu **5–15 menit** karena:
> - `mediapipe` (~50MB)  
> - `opencv-python-headless` (~30MB)
> - `numpy`, `Pillow`, dll

### LANGKAH 3 — Buat File `__init__.py`

```bash
# Windows
type nul > backend/__init__.py
type nul > database/__init__.py

# macOS / Linux
touch backend/__init__.py database/__init__.py
```

### LANGKAH 4 — Konfigurasi File `.env`

Buat file `.env` di root folder project untuk mengatur kredensial admin:

```env
ADMIN_USERNAME = "nama_admin_kamu"
ADMIN_PASSWORD = "password_rahasia_kamu"
FLASK_SECRET_KEY = "ganti-dengan-string-acak-yang-panjang"
```

> ⚠️ **Penting:** Jika file `.env` tidak dibuat, sistem akan menggunakan nilai default berikut:
> - Username: `admin`
> - Password: `admin123`
>
> **Sangat disarankan** untuk mengubah kredensial default sebelum digunakan di lingkungan produksi.
>
> 📌 File `.env` sudah otomatis diabaikan oleh Git (tercantum di `.gitignore`) sehingga **tidak akan ter-upload** ke repositori publik.

### LANGKAH 5 — Siapkan Aset Tanjak (PENTING)

Masukkan file PNG tanjak **dengan background transparan** ke folder `tanjak_assets/`:
```
tanjak_assets/
├── tanjak_lipatan.png    ← PNG transparan
├── tanjak_dondang.png    ← PNG transparan
└── tanjak_nobat.png      ← PNG transparan
```
> Jika belum ada file PNG, sistem akan menggunakan **placeholder sementara** untuk demo.

### LANGKAH 5 — Jalankan Server

```bash
python app.py
```

**Output terminal:**
```
═══════════════════════════════════════════════════════
  ✦  TanjakSyn – AI Cultural Heritage Platform  ✦
═══════════════════════════════════════════════════════
[DB] Database siap: .../database/tanjaksyn.db
  Server  : http://localhost:5000
  API     : http://localhost:5000/api/
  Mobile  : http://[YOUR-IP]:5000
═══════════════════════════════════════════════════════
 * Running on http://0.0.0.0:5000
 * Debug mode: on
```

### LANGKAH 6 — Buka Aplikasi

| Platform | URL |
|----------|-----|
| **Desktop** (Website) | `http://localhost:5000` |
| **Mobile** (Jaringan lokal) | `http://[IP-KOMPUTER]:5000` |

Untuk mencari IP komputer:
- **Windows**: `ipconfig` → lihat IPv4 Address
- **macOS/Linux**: `ifconfig` atau `ip addr`
- Contoh: `http://192.168.1.10:5000`

---

## 🌐 PERBEDAAN VIEW DESKTOP vs MOBILE

### Desktop (≥ 900px)
- **Sidebar tetap** di kiri (280px) dengan navigasi lengkap
- **Layout grid** multi-kolom (2–3 kolom)
- **Splash screen otomatis** dilewati setelah 2 detik
- **Statistik** di sidebar (total try-on, tanjak, UMKM)
- **Try-On layout**: Viewport kiri + Panel kontrol kanan

### Mobile (< 900px)
- **Top bar** dengan tombol hamburger menu
- **Sidebar** slide-in dari kiri (overlay)
- **Bottom navigation bar** 5 item
- **Splash screen penuh** dengan animasi
- **Layout single column** yang optimal di layar kecil
- **Aman area** (iPhone notch, Android gesture bar)

---

## 📡 API ENDPOINTS

### Endpoint Publik (Client)

| Method | Endpoint | Deskripsi |
|--------|----------|-----------|
| GET | `/` | Antarmuka pengguna client utama |
| GET | `/api/tanjak` | Daftar produk tanjak aktif & status asetnya |
| GET | `/api/tanjak/:id` | Detail data produk tanjak tertentu |
| POST | `/api/tryon` | Pemrosesan virtual try-on (input JSON base64 / multipart) |
| GET | `/api/result/:file` | Mengambil gambar hasil pemrosesan try-on |
| GET | `/api/education` | Daftar artikel edukasi warisan budaya |
| GET | `/api/umkm` | Daftar mitra pengrajin UMKM |
| GET | `/api/gallery` | Daftar foto di galeri publik |
| POST | `/api/gallery/save` | Menyimpan gambar hasil try-on ke galeri publik |
| GET | `/api/stats` | Informasi statistik singkat platform |
| GET | `/api/tanjak-asset/:file` | Menampilkan preview file gambar tanjak asli |

### Endpoint Panel Admin (Terproteksi Session)

| Method | Endpoint | Deskripsi |
|--------|----------|-----------|
| GET | `/admin` | Antarmuka panel dashboard admin (Auth Guarded) |
| POST | `/api/admin/login` | Proses login session admin |
| POST | `/api/admin/logout` | Proses logout session admin |
| GET | `/api/admin/check-session` | Cek validitas session admin aktif |
| GET | `/api/admin/tanjak` | Mengambil semua produk tanjak (termasuk status tidak aktif) |
| POST | `/api/admin/tanjak/add` | Menambah produk tanjak baru (mendukung upload berkas `.png`) |
| PUT | `/api/admin/tanjak/edit/:id` | Mengubah spesifikasi, harga, filosofi, atau gambar tanjak |
| DELETE | `/api/admin/tanjak/delete/:id` | Soft delete tanjak (mengubah flag status `is_active` menjadi 0) |
| POST | `/api/admin/umkm/add` | Menambah data profil pengrajin UMKM baru |
| PUT | `/api/admin/umkm/edit/:id` | Mengubah detail data profil pengrajin UMKM |
| DELETE | `/api/admin/umkm/delete/:id` | Menghapus permanen profil pengrajin UMKM |

---

## 🗃️ DATABASE SCHEMA

```
tanjak          → Katalog tanjak (id, name, file, scale, philosophy, price, artisan...)
umkm            → Pengrajin (artisan, location, whatsapp, rating, total_sold...)
education       → Konten edukasi (title, subtitle, content, icon, category...)
tryon_history   → Riwayat try-on (session_id, tanjak_id, proc_time, face_found...)
gallery         → Galeri publik (tryon_id, image_path, likes, is_public...)
```

---

## ❗ TROUBLESHOOTING

| Masalah | Solusi |
|---------|--------|
| `ModuleNotFoundError: backend` | Buat file `backend/__init__.py` dan `database/__init__.py` |
| `mediapipe` gagal install | Gunakan Python **3.9–3.11** (bukan 3.12+) |
| Wajah tidak terdeteksi | Foto harus frontal, pencahayaan cukup, wajah tidak tertutup |
| Tanjak tidak tampil di preview | File PNG belum ada di `tanjak_assets/` (normal, pakai placeholder) |
| Port 5000 sudah dipakai (macOS) | Ganti `port=5000` ke `5001` di `app.py` |
| `Cannot connect to server` | Pastikan `python app.py` sudah dijalankan |
| Database error | Hapus `database/tanjaksyn.db` lalu restart server |

---

## 🛠️ TEKNOLOGI

| Layer | Stack |
|-------|-------|
| **Backend** | Python 3.9+, Flask 3.0, Flask-CORS |
| **Database** | SQLite (via Python built-in) |
| **AI / CV** | MediaPipe Face Mesh (468 landmarks), OpenCV, NumPy |
| **Frontend** | HTML5, CSS3, Vanilla JS (tanpa framework) |
| **Font** | Cinzel Decorative, Cinzel, EB Garamond (Google Fonts) |
| **Responsive** | Mobile-first CSS Grid & Flexbox |
| **Deploy** | Gunicorn (production), Flask dev server |
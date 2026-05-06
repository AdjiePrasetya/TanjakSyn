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
│   ├── index.html                # 🌐 UI Responsif (Desktop + Mobile)
│   └── assets/
│       └── logo.png              # 🖼️ Logo TanjakSyn
│
├── tanjak_assets/                # 🎩 Taruh PNG tanjak transparan di sini
│   ├── tanjak_lipatan.png
│   ├── tanjak_dondang.png
│   └── tanjak_nobat.png
│
├── uploads/                      # 📁 Auto-created
└── outputs/                      # 📁 Auto-created (hasil try-on)
```

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

### LANGKAH 4 — Siapkan Aset Tanjak (PENTING)

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

| Method | Endpoint | Deskripsi |
|--------|----------|-----------|
| GET | `/` | Frontend HTML |
| GET | `/api/tanjak` | Daftar semua tanjak + status aset |
| GET | `/api/tanjak/:id` | Detail tanjak |
| POST | `/api/tryon` | Proses AI try-on (JSON base64) |
| POST | `/api/tryon` | Proses AI try-on (multipart form) |
| GET | `/api/result/:file` | Ambil gambar hasil |
| GET | `/api/education` | Daftar konten edukasi |
| GET | `/api/umkm` | Daftar pengrajin UMKM |
| GET | `/api/gallery` | Galeri publik |
| POST | `/api/gallery/save` | Simpan ke galeri |
| GET | `/api/stats` | Statistik platform |
| GET | `/api/tanjak-asset/:file` | Preview gambar tanjak |

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
"""
app.py – TanjakSyn Backend Server (Flask)
Endpoints: REST API + Penyedia (serving) file statis frontend

Modul ini adalah pusat orkestrasi web server TanjakSyn. Menggunakan framework Flask untuk melayani:
1. File statis web frontend (HTML, CSS, JS, Gambar).
2. REST API publik untuk mengakses data katalog tanjak, modul edukasi, profil pengrajin UMKM, dan galeri publik.
3. REST API publik interaktif untuk memicu engine AI Virtual Try-On Tanjak.
4. REST API terproteksi session (Admin Panel) untuk operasi CRUD katalog tanjak dan mitra UMKM.
"""

import os
import sys
import uuid
import json
from pathlib import Path
from flask import Flask, request, jsonify, send_from_directory, send_file, session
from flask_cors import CORS
from functools import wraps
from dotenv import load_dotenv

# ── MEMUAT ENVIRONMENT VARIABLES ──────────────────────────────────────────────────────
# Mengambil konfigurasi rahasia (.env) seperti secret key, kredensial admin, dan mode debug.
load_dotenv()

# ── PENYUSUNAN STRUKTUR DIREKTORI (PATH SETUP) ────────────────────────────────────────
# Menentukan lokasi direktori penting proyek secara dinamis berbasis letak file app.py.
BASE_DIR     = Path(__file__).parent
FRONTEND_DIR = BASE_DIR / "frontend"
TANJAK_DIR   = BASE_DIR / "tanjak_assets"  # Menyimpan gambar aset PNG tanjak untuk warping AI
UPLOAD_DIR   = BASE_DIR / "uploads"        # Menyimpan foto masukan pengguna (opsional/arsip)
OUTPUT_DIR   = BASE_DIR / "outputs"        # Menyimpan berkas gambar hasil pemasangan tanjak

sys.path.insert(0, str(BASE_DIR))

# Memastikan direktori penyimpanan aset fisik dan hasil olah gambar telah dibuat di disk
for d in [TANJAK_DIR, UPLOAD_DIR, OUTPUT_DIR]:
    d.mkdir(exist_ok=True)

# ── IMPOR MODUL INTERNAL DATABASE & PROSESOR AI ──────────────────────────────────────
from database.db import (
    init_db, get_all_tanjak, get_tanjak_by_id,
    get_all_education, get_all_umkm,
    save_tryon, save_gallery, get_gallery, get_stats,
    get_all_tanjak_admin, add_tanjak, update_tanjak, delete_tanjak,
    add_umkm, update_umkm, delete_umkm
)
from backend.ai_processor import process_tryon, bytes_to_b64

# ── INSTANSIASI APLIKASI FLASK ────────────────────────────────────────────────────────
# Mengatur folder static default Flask agar merujuk ke folder 'frontend'
app = Flask(__name__, static_folder=str(FRONTEND_DIR), static_url_path="")
# Secret key digunakan untuk mengenkripsi cookie session (paling krusial untuk fitur login admin)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "tanjaksyn-super-secret-key-12345")

# Mengaktifkan Cross-Origin Resource Sharing (CORS) untuk membolehkan request AJAX dari luar domain
CORS(app, resources={r"/api/*": {"origins": "*"}})


# ======================================================================================
# LAYANAN FILE STATIS FRONTEND (STATIC FRONTEND SERVING)
# ======================================================================================

@app.route("/")
def index():
    """
    Rute Utama (Homepage).
    
    Melayani pengiriman file index.html dari direktori frontend sebagai landing page utama.
    """
    return send_from_directory(FRONTEND_DIR, "index.html")


@app.route("/<path:path>")
def static_files(path):
    """
    Rute Penanganan Aset Statis Dinamis.
    
    Mengirimkan file aset statis (seperti gambar, file css, js) jika file tersebut
    secara fisik ada di dalam folder frontend. Jika tidak ditemukan, rute ini akan
    menerapkan fallback dengan mengirimkan index.html (sangat berguna untuk mendukung Single Page App Routing).
    
    Args:
        path (str): Sub-path file statis yang di-request.
    """
    if (FRONTEND_DIR / path).exists():
        return send_from_directory(FRONTEND_DIR, path)
    return send_from_directory(FRONTEND_DIR, "index.html")


# ======================================================================================
# API KATEGORI: TANJAK (PUBLIC ENDPOINTS)
# ======================================================================================

@app.route("/api/tanjak", methods=["GET"])
def api_tanjak_list():
    """
    Mengambil daftar semua tanjak aktif beserta status ketersediaan file gambarnya.
    
    Returns:
        JSON: Sukses status dan daftar dictionary data tanjak.
    """
    data = get_all_tanjak()
    # Menambahkan bendera keaktifan file fisik secara dinamis di server
    for t in data:
        t["asset_available"] = (TANJAK_DIR / t["file"]).exists()
    return jsonify({"success": True, "data": data})


@app.route("/api/tanjak/<tid>", methods=["GET"])
def api_tanjak_detail(tid):
    """
    Mengambil data detail satu tanjak berdasarkan ID uniknya.
    
    Args:
        tid (str): ID unik tanjak.
        
    Returns:
        JSON: Detail tanjak jika ditemukan, atau pesan error 404 jika absen.
    """
    t = get_tanjak_by_id(tid)
    if not t:
        return jsonify({"success": False, "message": "Tanjak tidak ditemukan"}), 404
    t["asset_available"] = (TANJAK_DIR / t["file"]).exists()
    return jsonify({"success": True, "data": t})


# ======================================================================================
# API KATEGORI: VIRTUAL TRY-ON (INTEGRASI ENGINE AI)
# ======================================================================================

@app.route("/api/tryon", methods=["POST"])
def api_tryon():
    """
    Endpoint pemrosesan utama Virtual Try-On Tanjak menggunakan AI.
    
    Mendukung dua format payload input:
    1. multipart/form-data: Untuk upload file fisik ('person_image') dan field form ('tanjak_id').
    2. application/json: Untuk pengiriman data gambar berupa string Base64.
    
    Langkah Alur Kerja:
    1. Ekstraksi byte data gambar orang dan ID tanjak yang di-request.
    2. Ambil parameter geometri warping (skala & offset vertikal) tanjak terkait dari database.
    3. Panggil engine pemrosesan citra `process_tryon` dari modul ai_processor.
    4. Simpan gambar hasil pemasangan (PNG transparan) ke dalam folder /outputs.
    5. Catat log transaksi tryon ke dalam database SQLite.
    6. Kembalikan respons berupa data string Base64 gambar akhir dan URL akses statis hasil.
    
    Returns:
        JSON: Objek respons sukses beserta representasi citra hasil fitting.
    """
    try:
        # Membuat identifier sesi transaksi 8 karakter unik untuk penamaan file
        session_id = str(uuid.uuid4())[:8]
        person_bytes = None

        # ── Ekstraksi Payload Input ──
        if request.content_type and "multipart" in request.content_type:
            # Skenario A: Upload form-data konvensional (dari form HTML biasa)
            if "person_image" not in request.files:
                return jsonify({"success": False, "message": "File gambar tidak ditemukan"}), 400
            person_bytes = request.files["person_image"].read()
            tanjak_id    = request.form.get("tanjak_id", "tanjak_lipatan_bugis")
        else:
            # Skenario B: Payload JSON (umum digunakan oleh webcam capture Base64)
            data = request.get_json(force=True)
            if not data or "person_image" not in data:
                return jsonify({"success": False, "message": "Data tidak valid"}), 400
            b64 = data["person_image"]
            # Membersihkan header metadata base64 jika ada (misal: "data:image/jpeg;base64,...")
            if "," in b64:
                b64 = b64.split(",")[1]
            import base64 as _base64
            person_bytes = _base64.b64decode(b64)
            tanjak_id    = data.get("tanjak_id", "tanjak_lipatan_bugis")

        # ── Mengambil Parameter Konfigurasi Tanjak dari DB ──
        tanjak = get_tanjak_by_id(tanjak_id)
        # Fallback jika ID tanjak tidak ada di database katalog
        if not tanjak:
            tanjak = get_tanjak_by_id("tanjak_lipatan_bugis") or {
                "id": "tanjak_lipatan_bugis", "name": "Tanjak Lipatan Bugis",
                "file": "tanjak_lipatan_bugis.png", "scale": 2.6, "v_offset": 0.35,
                "philosophy": "Simbol Keberanian dan Kepemimpinan. Setiap lipatan mencerminkan kebijaksanaan pemimpin Melayu yang harus mampu memimpin dengan adil dan tegas.",
                "price": 50000, "artisan": "Pak Hamdan", "artisan_wa": "6281234567890",
            }

        # ── Memuat Berkas Citra Ornamen Tanjak ──
        tanjak_path = TANJAK_DIR / tanjak["file"]
        if tanjak_path.exists():
            with open(tanjak_path, "rb") as f:
                tanjak_bytes = f.read()
        else:
            tanjak_bytes = None  # ai_processor akan otomatis membuat segitiga placeholder

        # ── Mengeksekusi Pipeline AI Try-On ──
        result_bytes, meta = process_tryon(
            person_bytes,
            tanjak_bytes if tanjak_bytes else b"",
            scale    = float(tanjak.get("scale",    2.6)),
            v_offset = float(tanjak.get("v_offset", 0.35)),
        )

        # ── Menyimpan Gambar Hasil ke Media Penyimpanan Lokal ──
        out_name = f"{session_id}_{tanjak_id}.png"
        out_path = OUTPUT_DIR / out_name
        with open(out_path, "wb") as f:
            f.write(result_bytes)

        # ── Mencatat Transaksi di Database SQLite ──
        tryon_id = save_tryon(session_id, tanjak_id, str(out_path), 1, meta["proc_time"])

        # ── Menyusun JSON Response ──
        return jsonify({
            "success":       True,
            "result_image":  bytes_to_b64(result_bytes),
            "result_url":    f"/api/result/{out_name}",
            "tryon_id":      tryon_id,
            "proc_time":     meta["proc_time"],
            "strategy":      meta["strategy"],
            "tanjak_info": {
                "id":         tanjak["id"],
                "name":       tanjak["name"],
                "philosophy": tanjak.get("philosophy", ""),
                "price":      tanjak.get("price", 50000),
                "artisan":    tanjak.get("artisan", ""),
                "artisan_wa": tanjak.get("artisan_wa", ""),
                "commission": tanjak.get("commission", 0.10),
            },
        })

    except ValueError as e:
        # Menangani error validasi gambar (wajah miring/tidak terdeteksi)
        return jsonify({"success": False, "message": str(e)}), 422
    except Exception as e:
        # Menangkap error sistem / server runtime lainnya
        import traceback; traceback.print_exc()
        return jsonify({"success": False, "message": f"Server error: {str(e)}"}), 500


@app.route("/api/result/<filename>")
def serve_result(filename):
    """
    Rute pengaksesan file citra hasil olah AI virtual try-on.
    
    Args:
        filename (str): Nama file gambar hasil.
    """
    return send_from_directory(OUTPUT_DIR, filename)


# ======================================================================================
# API KATEGORI: PUBLIC READ INFORMATION
# ======================================================================================

@app.route("/api/gallery", methods=["GET"])
def api_gallery():
    """
    Mengambil daftar foto hasil kreasi try-on pengguna yang telah dipublikasikan.
    """
    items = get_gallery(limit=20)
    return jsonify({"success": True, "data": items})


@app.route("/api/gallery/save", methods=["POST"])
def api_gallery_save():
    """
    Memublikasikan foto kreasi try-on pengguna ke galeri umum.
    """
    data     = request.get_json(force=True)
    tryon_id = data.get("tryon_id")
    img_path = data.get("image_path", "")
    tid      = data.get("tanjak_id", "")
    if tryon_id:
        save_gallery(tryon_id, img_path, tid)
    return jsonify({"success": True})


@app.route("/api/education", methods=["GET"])
def api_education():
    """
    Mengambil semua artikel edukasi dan kebudayaan tanjak Melayu.
    """
    return jsonify({"success": True, "data": get_all_education()})


@app.route("/api/umkm", methods=["GET"])
def api_umkm():
    """
    Mengambil semua daftar pengrajin UMKM mitra yang terdaftar beserta data produknya.
    """
    return jsonify({"success": True, "data": get_all_umkm()})


@app.route("/api/stats", methods=["GET"])
def api_stats():
    """
    Mengambil ringkasan statistik server (jumlah tryon, UMKM, galeri, tanjak) untuk dashboard.
    """
    return jsonify({"success": True, "data": get_stats()})


@app.route("/api/tanjak-asset/<filename>")
def tanjak_asset(filename):
    """
    Melayani pengiriman berkas gambar mentah ornamen tanjak dari folder tanjak_assets.
    
    Args:
        filename (str): Nama berkas gambar tanjak.
    """
    if (TANJAK_DIR / filename).exists():
        return send_from_directory(TANJAK_DIR, filename)
    return jsonify({"error": "not found"}), 404


# ======================================================================================
# ROUTE & ENDPOINT PANEL ADMIN (ADMIN SECURED ACTIONS)
# ======================================================================================

def admin_required(f):
    """
    Decorator Python untuk melindungi API khusus administrator.
    
    Memeriksa variabel session "logged_in". Jika bernilai palsu atau kosong,
    sistem otomatis menolak akses dan mengembalikan respons JSON 401 Unauthorized.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("logged_in"):
            return jsonify({"success": False, "message": "Unauthorized. Silakan login terlebih dahulu."}), 401
        return f(*args, **kwargs)
    return decorated_function


@app.route("/admin")
def admin_page():
    """
    Melayani pengiriman halaman antarmuka web panel admin (admin.html).
    """
    return send_from_directory(FRONTEND_DIR, "admin.html")


@app.route("/api/admin/login", methods=["POST"])
def api_admin_login():
    """
    API Autentikasi Login Admin.
    
    Membandingkan kredensial masukan dengan variabel lingkungan ADMIN_USERNAME dan ADMIN_PASSWORD.
    Jika login sukses, status 'logged_in' diset True di dalam session terenkripsi Flask.
    """
    data = request.get_json(force=True) or {}
    username = data.get("username")
    password = data.get("password")
    
    # Mengambil nilai kredensial dari .env dengan fallback nilai default
    admin_user = os.environ.get("ADMIN_USERNAME", "admin")
    admin_pass = os.environ.get("ADMIN_PASSWORD", "admin123")
    
    if username == admin_user and password == admin_pass:
        session["logged_in"] = True
        return jsonify({"success": True, "message": "Login berhasil"})
    return jsonify({"success": False, "message": "Username atau password salah"}), 401


@app.route("/api/admin/logout", methods=["POST"])
def api_admin_logout():
    """
    API Keluar Sesi Admin (Logout).
    Menghapus kunci session 'logged_in'.
    """
    session.pop("logged_in", None)
    return jsonify({"success": True, "message": "Logout berhasil"})


@app.route("/api/admin/check-session", methods=["GET"])
def api_admin_check_session():
    """
    API Pemeriksa Satus Autentikasi Sesi Admin Aktif.
    """
    return jsonify({"success": True, "logged_in": session.get("logged_in", False)})


@app.route("/api/admin/tanjak", methods=["GET"])
@admin_required
def api_admin_tanjak_list():
    """
    API Pengambil Seluruh Data Tanjak termasuk yang nonaktif (Hanya Admin).
    """
    data = get_all_tanjak_admin()
    for t in data:
        t["asset_available"] = (TANJAK_DIR / t["file"]).exists()
    return jsonify({"success": True, "data": data})


@app.route("/api/admin/tanjak/add", methods=["POST"])
@admin_required
def api_admin_tanjak_add():
    """
    API Menambahkan Katalog Tanjak Baru beserta Upload File Aset Gambar (Hanya Admin).
    """
    try:
        # Mendukung form-data dengan berkas file, maupun JSON konvensional
        if request.content_type and "multipart" in request.content_type:
            tid = request.form.get("id")
            name = request.form.get("name")
            scale = float(request.form.get("scale", 2.6))
            v_offset = float(request.form.get("v_offset", 0.35))
            philosophy = request.form.get("philosophy", "")
            origin = request.form.get("origin", "")
            usage = request.form.get("usage", "")
            price = int(request.form.get("price", 50000))
            artisan = request.form.get("artisan", "")
            artisan_wa = request.form.get("artisan_wa", "")
            commission = float(request.form.get("commission", 0.10))
            image_file = request.files.get("image")
        else:
            data = request.get_json(force=True) or {}
            tid = data.get("id")
            name = data.get("name")
            scale = float(data.get("scale", 2.6))
            v_offset = float(data.get("v_offset", 0.35))
            philosophy = data.get("philosophy", "")
            origin = data.get("origin", "")
            usage = data.get("usage", "")
            price = int(data.get("price", 50000))
            artisan = data.get("artisan", "")
            artisan_wa = data.get("artisan_wa", "")
            commission = float(data.get("commission", 0.10))
            image_file = None

        if not tid or not name:
            return jsonify({"success": False, "message": "ID dan Nama Tanjak harus diisi"}), 400

        # Menangani unggahan file gambar ornamen tanjak
        file_name = f"{tid}.png"
        if image_file:
            image_path = TANJAK_DIR / file_name
            image_file.save(image_path)
        else:
            file_name = "tanjak_lipatan_bugis.png"  # Fallback default asset

        add_tanjak(tid, name, file_name, scale, v_offset, philosophy, origin, usage, price, artisan, artisan_wa, commission)
        return jsonify({"success": True, "message": "Tanjak berhasil ditambahkan", "id": tid})
    except Exception as e:
        return jsonify({"success": False, "message": f"Gagal menambahkan tanjak: {str(e)}"}), 500


@app.route("/api/admin/tanjak/edit/<tid>", methods=["PUT", "POST"])
@admin_required
def api_admin_tanjak_edit(tid):
    """
    API Memperbarui/Mengedit Katalog Tanjak yang Ada (Hanya Admin).
    
    Args:
        tid (str): ID unik tanjak yang diedit.
    """
    try:
        existing = get_tanjak_by_id(tid)
        if not existing:
            return jsonify({"success": False, "message": "Tanjak tidak ditemukan"}), 404

        if request.content_type and "multipart" in request.content_type:
            name = request.form.get("name", existing["name"])
            scale = float(request.form.get("scale", existing["scale"]))
            v_offset = float(request.form.get("v_offset", existing["v_offset"]))
            philosophy = request.form.get("philosophy", existing["philosophy"])
            origin = request.form.get("origin", existing["origin"])
            usage = request.form.get("usage", existing["usage"])
            price = int(request.form.get("price", existing["price"]))
            artisan = request.form.get("artisan", existing["artisan"])
            artisan_wa = request.form.get("artisan_wa", existing["artisan_wa"])
            commission = float(request.form.get("commission", existing["commission"]))
            is_active = int(request.form.get("is_active", existing["is_active"]))
            image_file = request.files.get("image")
        else:
            data = request.get_json(force=True) or {}
            name = data.get("name", existing["name"])
            scale = float(data.get("scale", existing["scale"]))
            v_offset = float(data.get("v_offset", existing["v_offset"]))
            philosophy = data.get("philosophy", existing["philosophy"])
            origin = data.get("origin", existing["origin"])
            usage = data.get("usage", existing["usage"])
            price = int(data.get("price", existing["price"]))
            artisan = data.get("artisan", existing["artisan"])
            artisan_wa = data.get("artisan_wa", existing["artisan_wa"])
            commission = float(data.get("commission", existing["commission"]))
            is_active = int(data.get("is_active", existing["is_active"]))
            image_file = None

        file_name = existing["file"]
        # Jika administrator mengunggah berkas gambar pengganti baru
        if image_file:
            file_name = f"{tid}.png"
            image_path = TANJAK_DIR / file_name
            image_file.save(image_path)

        update_tanjak(tid, name, file_name, scale, v_offset, philosophy, origin, usage, price, artisan, artisan_wa, commission, is_active)
        return jsonify({"success": True, "message": "Tanjak berhasil diperbarui"})
    except Exception as e:
        return jsonify({"success": False, "message": f"Gagal memperbarui tanjak: {str(e)}"}), 500


@app.route("/api/admin/tanjak/delete/<tid>", methods=["DELETE", "POST"])
@admin_required
def api_admin_tanjak_delete(tid):
    """
    API Menonaktifkan Tanjak (Soft Delete) agar tidak tampil di beranda utama (Hanya Admin).
    
    Args:
        tid (str): ID unik tanjak yang dihapus lunak.
    """
    try:
        delete_tanjak(tid)
        return jsonify({"success": True, "message": "Tanjak berhasil dinonaktifkan (soft delete)"})
    except Exception as e:
        return jsonify({"success": False, "message": f"Gagal menghapus tanjak: {str(e)}"}), 500


@app.route("/api/admin/umkm/add", methods=["POST"])
@admin_required
def api_admin_umkm_add():
    """
    API Menambahkan Profil UMKM Pengrajin Baru (Hanya Admin).
    """
    try:
        data = request.get_json(force=True) or {}
        artisan = data.get("artisan")
        location = data.get("location", "")
        phone = data.get("phone", "")
        whatsapp = data.get("whatsapp", "")
        description = data.get("description", "")
        rating = float(data.get("rating", 5.0))
        total_sold = int(data.get("total_sold", 0))
        tanjak_id = data.get("tanjak_id")

        if not artisan:
            return jsonify({"success": False, "message": "Nama Pemilik/Artisan harus diisi"}), 400

        add_umkm(artisan, location, phone, whatsapp, description, rating, total_sold, tanjak_id)
        return jsonify({"success": True, "message": "UMKM berhasil ditambahkan"})
    except Exception as e:
        return jsonify({"success": False, "message": f"Gagal menambahkan UMKM: {str(e)}"}), 500


@app.route("/api/admin/umkm/edit/<int:umkm_id>", methods=["PUT", "POST"])
@admin_required
def api_admin_umkm_edit(umkm_id):
    """
    API Memperbarui Profil Mitra UMKM Pengrajin (Hanya Admin).
    
    Args:
        umkm_id (int): ID unik baris UMKM.
    """
    try:
        data = request.get_json(force=True) or {}
        artisan = data.get("artisan")
        location = data.get("location")
        phone = data.get("phone")
        whatsapp = data.get("whatsapp")
        description = data.get("description")
        rating = float(data.get("rating", 5.0))
        total_sold = int(data.get("total_sold", 0))
        tanjak_id = data.get("tanjak_id")

        if not artisan:
            return jsonify({"success": False, "message": "Nama Pemilik/Artisan harus diisi"}), 400

        update_umkm(umkm_id, artisan, location, phone, whatsapp, description, rating, total_sold, tanjak_id)
        return jsonify({"success": True, "message": "UMKM berhasil diperbarui"})
    except Exception as e:
        return jsonify({"success": False, "message": f"Gagal memperbarui UMKM: {str(e)}"}), 500


@app.route("/api/admin/umkm/delete/<int:umkm_id>", methods=["DELETE", "POST"])
@admin_required
def api_admin_umkm_delete(umkm_id):
    """
    API Menghapus Profil UMKM Pengrajin Secara Permanen (Hanya Admin).
    
    Args:
        umkm_id (int): ID unik baris UMKM yang dihapus permanen.
    """
    try:
        delete_umkm(umkm_id)
        return jsonify({"success": True, "message": "UMKM berhasil dihapus"})
    except Exception as e:
        return jsonify({"success": False, "message": f"Gagal menghapus UMKM: {str(e)}"}), 500


# ======================================================================================
# MENJALANKAN APLIKASI UTAMA (MAIN STARTUP ENTRYPOINT)
# ======================================================================================

if __name__ == "__main__":
    print("=" * 55)
    print("  ✦  TanjakSyn – AI Cultural Heritage Platform  ✦")
    print("=" * 55)
    
    # Memastikan tabel database dan seed data bawaan terbuat saat aplikasi pertama kali berjalan
    init_db()
    
    print("  Server  : http://localhost:5000")
    print("  API     : http://localhost:5000/api/")
    print("  Mobile  : http://[YOUR-IP]:5000")
    print("=" * 55)
    
    # debug=True: mengaktifkan auto-reload server saat kode diubah (dinonaktifkan reloader di docker untuk kestabilan)
    app.run(debug=True, host="0.0.0.0", port=5000, use_reloader=False)

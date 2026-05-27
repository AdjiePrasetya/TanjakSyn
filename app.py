"""
app.py – TanjakSyn Backend (Flask)
Endpoints: REST API + serve frontend static files
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

# Load environment variables from .env
load_dotenv()

# ── Path setup ────────────────────────────────────────────
BASE_DIR     = Path(__file__).parent
FRONTEND_DIR = BASE_DIR / "frontend"
TANJAK_DIR   = BASE_DIR / "tanjak_assets"
UPLOAD_DIR   = BASE_DIR / "uploads"
OUTPUT_DIR   = BASE_DIR / "outputs"

sys.path.insert(0, str(BASE_DIR))

for d in [TANJAK_DIR, UPLOAD_DIR, OUTPUT_DIR]:
    d.mkdir(exist_ok=True)

# ── DB & AI ───────────────────────────────────────────────
from database.db import (
    init_db, get_all_tanjak, get_tanjak_by_id,
    get_all_education, get_all_umkm,
    save_tryon, save_gallery, get_gallery, get_stats,
    get_all_tanjak_admin, add_tanjak, update_tanjak, delete_tanjak,
    add_umkm, update_umkm, delete_umkm
)
from backend.ai_processor import process_tryon, bytes_to_b64

# ── Flask App ─────────────────────────────────────────────
app = Flask(__name__, static_folder=str(FRONTEND_DIR), static_url_path="")
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "tanjaksyn-super-secret-key-12345")
CORS(app, resources={r"/api/*": {"origins": "*"}})

# ============================================================
# STATIC FRONTEND
# ============================================================

@app.route("/")
def index():
    return send_from_directory(FRONTEND_DIR, "index.html")

@app.route("/<path:path>")
def static_files(path):
    if (FRONTEND_DIR / path).exists():
        return send_from_directory(FRONTEND_DIR, path)
    return send_from_directory(FRONTEND_DIR, "index.html")


# ============================================================
# API: TANJAK
# ============================================================

@app.route("/api/tanjak", methods=["GET"])
def api_tanjak_list():
    data = get_all_tanjak()
    # Tambahkan flag apakah file aset tersedia
    for t in data:
        t["asset_available"] = (TANJAK_DIR / t["file"]).exists()
    return jsonify({"success": True, "data": data})


@app.route("/api/tanjak/<tid>", methods=["GET"])
def api_tanjak_detail(tid):
    t = get_tanjak_by_id(tid)
    if not t:
        return jsonify({"success": False, "message": "Tanjak tidak ditemukan"}), 404
    t["asset_available"] = (TANJAK_DIR / t["file"]).exists()
    return jsonify({"success": True, "data": t})


# ============================================================
# API: TRY-ON
# ============================================================

@app.route("/api/tryon", methods=["POST"])
def api_tryon():
    try:
        session_id = str(uuid.uuid4())[:8]

        # ── Ambil gambar orang ───────────────────────────
        person_bytes = None

        if request.content_type and "multipart" in request.content_type:
            # Form-data upload
            if "person_image" not in request.files:
                return jsonify({"success": False, "message": "File gambar tidak ditemukan"}), 400
            person_bytes = request.files["person_image"].read()
            tanjak_id    = request.form.get("tanjak_id", "tanjak_lipatan")
        else:
            # JSON base64
            data = request.get_json(force=True)
            if not data or "person_image" not in data:
                return jsonify({"success": False, "message": "Data tidak valid"}), 400
            b64 = data["person_image"]
            if "," in b64:
                b64 = b64.split(",")[1]
            import base64 as _b64
            person_bytes = _b64.b64decode(b64)
            tanjak_id    = data.get("tanjak_id", "tanjak_lipatan")

        # ── Ambil config tanjak dari DB ──────────────────
        tanjak = get_tanjak_by_id(tanjak_id)
        if not tanjak:
            tanjak = get_tanjak_by_id("tanjak_lipatan") or {
                "id": "tanjak_lipatan", "name": "Tanjak Lipatan",
                "file": "tanjak_lipatan.png", "scale": 2.6, "v_offset": 0.35,
                "philosophy": "Simbol Keberanian dan Kepemimpinan",
                "price": 50000, "artisan": "Pak Hamdan", "artisan_wa": "6281234567890",
            }

        # ── Load tanjak image bytes ──────────────────────
        tanjak_path = TANJAK_DIR / tanjak["file"]
        if tanjak_path.exists():
            with open(tanjak_path, "rb") as f:
                tanjak_bytes = f.read()
        else:
            tanjak_bytes = None  # ai_processor akan buat placeholder

        # ── Proses AI ────────────────────────────────────
        result_bytes, meta = process_tryon(
            person_bytes,
            tanjak_bytes if tanjak_bytes else b"",
            scale    = float(tanjak.get("scale",    2.6)),
            v_offset = float(tanjak.get("v_offset", 0.35)),
        )

        # ── Simpan hasil ke disk ─────────────────────────
        out_name = f"{session_id}_{tanjak_id}.png"
        out_path = OUTPUT_DIR / out_name
        with open(out_path, "wb") as f:
            f.write(result_bytes)

        # ── Simpan ke DB ─────────────────────────────────
        tryon_id = save_tryon(session_id, tanjak_id, str(out_path), 1, meta["proc_time"])

        # ── Kembalikan response ──────────────────────────
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
        return jsonify({"success": False, "message": str(e)}), 422
    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({"success": False, "message": f"Server error: {str(e)}"}), 500


@app.route("/api/result/<filename>")
def serve_result(filename):
    return send_from_directory(OUTPUT_DIR, filename)


# ============================================================
# API: GALLERY
# ============================================================

@app.route("/api/gallery", methods=["GET"])
def api_gallery():
    items = get_gallery(limit=20)
    return jsonify({"success": True, "data": items})


@app.route("/api/gallery/save", methods=["POST"])
def api_gallery_save():
    data     = request.get_json(force=True)
    tryon_id = data.get("tryon_id")
    img_path = data.get("image_path", "")
    tid      = data.get("tanjak_id", "")
    if tryon_id:
        save_gallery(tryon_id, img_path, tid)
    return jsonify({"success": True})


# ============================================================
# API: EDUCATION
# ============================================================

@app.route("/api/education", methods=["GET"])
def api_education():
    return jsonify({"success": True, "data": get_all_education()})


# ============================================================
# API: UMKM
# ============================================================

@app.route("/api/umkm", methods=["GET"])
def api_umkm():
    return jsonify({"success": True, "data": get_all_umkm()})


# ============================================================
# API: STATS / DASHBOARD
# ============================================================

@app.route("/api/stats", methods=["GET"])
def api_stats():
    return jsonify({"success": True, "data": get_stats()})


# ============================================================
# ASSETS: serve tanjak preview images
# ============================================================

@app.route("/api/tanjak-asset/<filename>")
def tanjak_asset(filename):
    if (TANJAK_DIR / filename).exists():
        return send_from_directory(TANJAK_DIR, filename)
    return jsonify({"error": "not found"}), 404


# ============================================================
# ADMIN ROUTE & API ENDPOINTS
# ============================================================

# Decorator to secure admin routes
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("logged_in"):
            return jsonify({"success": False, "message": "Unauthorized. Silakan login terlebih dahulu."}), 401
        return f(*args, **kwargs)
    return decorated_function

# Route to serve admin static page
@app.route("/admin")
def admin_page():
    return send_from_directory(FRONTEND_DIR, "admin.html")

# API: Admin Login
@app.route("/api/admin/login", methods=["POST"])
def api_admin_login():
    data = request.get_json(force=True) or {}
    username = data.get("username")
    password = data.get("password")
    
    admin_user = os.environ.get("ADMIN_USERNAME", "admin")
    admin_pass = os.environ.get("ADMIN_PASSWORD", "admin123")
    
    if username == admin_user and password == admin_pass:
        session["logged_in"] = True
        return jsonify({"success": True, "message": "Login berhasil"})
    return jsonify({"success": False, "message": "Username atau password salah"}), 401

# API: Admin Logout
@app.route("/api/admin/logout", methods=["POST"])
def api_admin_logout():
    session.pop("logged_in", None)
    return jsonify({"success": True, "message": "Logout berhasil"})

# API: Admin Session Check
@app.route("/api/admin/check-session", methods=["GET"])
def api_admin_check_session():
    return jsonify({"success": True, "logged_in": session.get("logged_in", False)})

# API: Admin Get All Tanjaks (including inactive ones)
@app.route("/api/admin/tanjak", methods=["GET"])
@admin_required
def api_admin_tanjak_list():
    data = get_all_tanjak_admin()
    for t in data:
        t["asset_available"] = (TANJAK_DIR / t["file"]).exists()
    return jsonify({"success": True, "data": data})

# API: Admin Add Tanjak
@app.route("/api/admin/tanjak/add", methods=["POST"])
@admin_required
def api_admin_tanjak_add():
    try:
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

        # Handle image file upload
        file_name = f"{tid}.png"
        if image_file:
            image_path = TANJAK_DIR / file_name
            image_file.save(image_path)
        else:
            file_name = "tanjak_lipatan_bugis.png" # default or fallback

        add_tanjak(tid, name, file_name, scale, v_offset, philosophy, origin, usage, price, artisan, artisan_wa, commission)
        return jsonify({"success": True, "message": "Tanjak berhasil ditambahkan", "id": tid})
    except Exception as e:
        return jsonify({"success": False, "message": f"Gagal menambahkan tanjak: {str(e)}"}), 500

# API: Admin Edit Tanjak
@app.route("/api/admin/tanjak/edit/<tid>", methods=["PUT", "POST"])
@admin_required
def api_admin_tanjak_edit(tid):
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
        if image_file:
            file_name = f"{tid}.png"
            image_path = TANJAK_DIR / file_name
            image_file.save(image_path)

        update_tanjak(tid, name, file_name, scale, v_offset, philosophy, origin, usage, price, artisan, artisan_wa, commission, is_active)
        return jsonify({"success": True, "message": "Tanjak berhasil diperbarui"})
    except Exception as e:
        return jsonify({"success": False, "message": f"Gagal memperbarui tanjak: {str(e)}"}), 500

# API: Admin Delete Tanjak
@app.route("/api/admin/tanjak/delete/<tid>", methods=["DELETE", "POST"])
@admin_required
def api_admin_tanjak_delete(tid):
    try:
        delete_tanjak(tid)
        return jsonify({"success": True, "message": "Tanjak berhasil dinonaktifkan (soft delete)"})
    except Exception as e:
        return jsonify({"success": False, "message": f"Gagal menghapus tanjak: {str(e)}"}), 500

# API: Admin Add UMKM
@app.route("/api/admin/umkm/add", methods=["POST"])
@admin_required
def api_admin_umkm_add():
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

# API: Admin Edit UMKM
@app.route("/api/admin/umkm/edit/<int:umkm_id>", methods=["PUT", "POST"])
@admin_required
def api_admin_umkm_edit(umkm_id):
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

# API: Admin Delete UMKM
@app.route("/api/admin/umkm/delete/<int:umkm_id>", methods=["DELETE", "POST"])
@admin_required
def api_admin_umkm_delete(umkm_id):
    try:
        delete_umkm(umkm_id)
        return jsonify({"success": True, "message": "UMKM berhasil dihapus"})
    except Exception as e:
        return jsonify({"success": False, "message": f"Gagal menghapus UMKM: {str(e)}"}), 500


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":
    print("=" * 55)
    print("  ✦  TanjakSyn – AI Cultural Heritage Platform  ✦")
    print("=" * 55)
    init_db()
    print("  Server  : http://localhost:5000")
    print("  API     : http://localhost:5000/api/")
    print("  Mobile  : http://[YOUR-IP]:5000")
    print("=" * 55)
    app.run(debug=True, host="0.0.0.0", port=5000, use_reloader=False)

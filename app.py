"""
app.py – TanjakSyn Backend (Flask)
Endpoints: REST API + serve frontend static files
"""

import os
import sys
import uuid
import json
from pathlib import Path
from flask import Flask, request, jsonify, send_from_directory, send_file
from flask_cors import CORS

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
    save_tryon, save_gallery, get_gallery, get_stats
)
from backend.ai_processor import process_tryon, bytes_to_b64

# ── Flask App ─────────────────────────────────────────────
app = Flask(__name__, static_folder=str(FRONTEND_DIR), static_url_path="")
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

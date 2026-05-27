"""
database/db.py
Modul database SQLite untuk TanjakSyn
Menyimpan: katalog tanjak, UMKM, edukasi, riwayat try-on
"""

import sqlite3
import os
import json
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), 'tanjaksyn.db')


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    """Buat semua tabel dan isi data awal"""
    conn = get_connection()
    cur = conn.cursor()

    # ── Tabel tanjak (katalog utama)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS tanjak (
        id          TEXT PRIMARY KEY,
        name        TEXT NOT NULL,
        file        TEXT NOT NULL,
        scale       REAL DEFAULT 2.6,
        v_offset    REAL DEFAULT 0.35,
        philosophy  TEXT,
        origin      TEXT,
        usage       TEXT,
        price       INTEGER DEFAULT 50000,
        artisan     TEXT,
        artisan_wa  TEXT,
        commission  REAL DEFAULT 0.10,
        is_active   INTEGER DEFAULT 1,
        sort_order  INTEGER DEFAULT 0,
        created_at  TEXT DEFAULT (datetime('now'))
    )""")

    # ── Tabel umkm
    cur.execute("""
    CREATE TABLE IF NOT EXISTS umkm (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        artisan     TEXT NOT NULL,
        location    TEXT,
        phone       TEXT,
        whatsapp    TEXT,
        description TEXT,
        rating      REAL DEFAULT 5.0,
        total_sold  INTEGER DEFAULT 0,
        tanjak_id   TEXT REFERENCES tanjak(id),
        created_at  TEXT DEFAULT (datetime('now'))
    )""")

    # ── Tabel edukasi
    cur.execute("""
    CREATE TABLE IF NOT EXISTS education (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        title       TEXT NOT NULL,
        subtitle    TEXT,
        content     TEXT,
        icon        TEXT DEFAULT '📖',
        category    TEXT DEFAULT 'filosofi',
        sort_order  INTEGER DEFAULT 0
    )""")

    # ── Tabel riwayat try-on
    cur.execute("""
    CREATE TABLE IF NOT EXISTS tryon_history (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        session_id  TEXT,
        tanjak_id   TEXT REFERENCES tanjak(id),
        result_path TEXT,
        face_found  INTEGER DEFAULT 1,
        proc_time   REAL,
        created_at  TEXT DEFAULT (datetime('now'))
    )""")

    # ── Tabel galeri (hasil tryon yang disimpan publik)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS gallery (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        tryon_id    INTEGER REFERENCES tryon_history(id),
        image_path  TEXT,
        tanjak_id   TEXT,
        likes       INTEGER DEFAULT 0,
        is_public   INTEGER DEFAULT 1,
        created_at  TEXT DEFAULT (datetime('now'))
    )""")

    conn.commit()
    _seed_data(cur, conn)
    conn.close()
    print("[DB] Database siap:", DB_PATH)


def _seed_data(cur, conn):
    """Isi data awal jika tabel kosong"""

    # Seed tanjak
    cur.execute("SELECT COUNT(*) FROM tanjak")
    if cur.fetchone()[0] == 0:
        tanjak_data = [
            ("tanjak_lipatan_bugis", "Tanjak Lipatan Bugis",   "tanjak_lipatan_bugis.png",  2.6, 0.35,
             "Simbol Keberanian dan Kepemimpinan. Setiap lipatan mencerminkan kebijaksanaan pemimpin Melayu yang harus mampu memimpin dengan adil dan tegas.",
             "Riau", "Upacara Adat & Pesta Pernikahan", 50000, "Pak Hamdan", "6281234567890", 0.10, 1, 1),
            ("tanjak_lipatan_pontianak", "Tanjak Lipatan Pontianak",   "tanjak_lipatan_pontianak.png",  2.4, 0.30,
             "Simbol Kesucian dan Ketulusan Hati. Tanjak Lipatan Pontianak melambangkan kemurnian niat dalam setiap tindakan, warisan budaya bangsawan Melayu.",
             "Kepulauan Riau", "Acara Resmi & Keagamaan", 75000, "Bu Fatimah", "6289876543210", 0.10, 1, 2),
            ("tanjak_lipatan_sambas",   "Tanjak Lipatan Sambas",     "tanjak_lipatan_sambas.png",    2.8, 0.40,
             "Simbol Kemuliaan dan Kehormatan Tertinggi. Dipakai oleh raja dan bangsawan dalam upacara kenegaraan sebagai tanda martabat dan wibawa.",
             "Johor-Melayu", "Upacara Kerajaan & Kenegaraan", 100000, "Pak Ismail", "6285551234567", 0.10, 1, 3),
        ]
        cur.executemany("""
            INSERT INTO tanjak (id,name,file,scale,v_offset,philosophy,origin,usage,price,artisan,artisan_wa,commission,is_active,sort_order)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, tanjak_data)

    # Seed edukasi
    cur.execute("SELECT COUNT(*) FROM education")
    if cur.fetchone()[0] == 0:
        edu_data = [
            ("Dua Cara Memasang Tanjak", "Tradisi Yonder & Padinuk",
             "Tanjak dapat dipasang dengan dua metode berbeda yang mencerminkan status dan asal-usul pemakainya. Metode Yonder digunakan oleh kaum bangsawan, sementara Padinuk untuk kalangan umum.",
             "🎓", "teknik", 1),
            ("Makna Warna & Motif", "Kode Tersembunyi dalam Kain",
             "Setiap warna tanjak memiliki makna mendalam: Merah melambangkan keberanian, Kuning emas untuk kemuliaan raja, Hitam untuk keteguhan hati. Motif batik yang menghiasi juga menyimpan pesan leluhur.",
             "🌈", "filosofi", 2),
            ("Sejarah Kesultanan Melayu", "Warisan 7 Abad Budaya",
             "Tanjak telah digunakan sejak abad ke-15 dalam Kesultanan Malaka dan terus berkembang di seluruh kepulauan Melayu. Setiap kerajaan memiliki gaya tanjak khasnya sendiri.",
             "🏛️", "sejarah", 3),
            ("Tanjak di Era Modern", "Melestarikan Identitas",
             "Di era globalisasi, tanjak kini hadir dalam berbagai acara modern mulai dari wisuda, pernikahan, hingga fashion show internasional sebagai simbol kebanggaan identitas Melayu.",
             "✨", "modern", 4),
        ]
        cur.executemany("""
            INSERT INTO education (title,subtitle,content,icon,category,sort_order)
            VALUES (?,?,?,?,?,?)
        """, edu_data)

    # Seed UMKM
    cur.execute("SELECT COUNT(*) FROM umkm")
    if cur.fetchone()[0] == 0:
        umkm_data = [
            ("Pak Hamdan", "Pekanbaru, Riau", "0812-3456-7890", "6281234567890",
            "Pengrajin tanjak generasi ke-3 ...", 4.9, 127, "tanjak_lipatan_bugis"),
            ("Bu Fatimah", "Tanjungpinang, Kepri", "0898-7654-3210", "6289876543210",
            "Maestro tanjak wanita pertama ...", 4.8, 89, "tanjak_lipatan_pontianak"),  # ✅ diganti
            ("Pak Ismail", "Batam, Kepri", "0855-5123-4567", "6285551234567",
            "Pemenang penghargaan ...", 5.0, 45, "tanjak_lipatan_sambas"),              # ✅ diganti
        ]
        cur.executemany("""
            INSERT INTO umkm (artisan,location,phone,whatsapp,description,rating,total_sold,tanjak_id)
            VALUES (?,?,?,?,?,?,?,?)
        """, umkm_data)

    conn.commit()


# ── CRUD helpers ──────────────────────────────────────────

def get_all_tanjak():
    conn = get_connection()
    rows = conn.execute("SELECT * FROM tanjak WHERE is_active=1 ORDER BY sort_order").fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_tanjak_by_id(tid):
    conn = get_connection()
    row = conn.execute("SELECT * FROM tanjak WHERE id=?", (tid,)).fetchone()
    conn.close()
    return dict(row) if row else None

def get_all_education():
    conn = get_connection()
    rows = conn.execute("SELECT * FROM education ORDER BY sort_order").fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_all_umkm():
    conn = get_connection()
    rows = conn.execute("""
        SELECT u.*, t.name as tanjak_name, t.price as tanjak_price
        FROM umkm u LEFT JOIN tanjak t ON u.tanjak_id = t.id
        ORDER BY u.rating DESC
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def save_tryon(session_id, tanjak_id, result_path, face_found, proc_time):
    conn = get_connection()
    cur = conn.execute("""
        INSERT INTO tryon_history (session_id, tanjak_id, result_path, face_found, proc_time)
        VALUES (?,?,?,?,?)
    """, (session_id, tanjak_id, result_path, face_found, proc_time))
    conn.commit()
    tryon_id = cur.lastrowid
    conn.close()
    return tryon_id

def save_gallery(tryon_id, image_path, tanjak_id):
    conn = get_connection()
    conn.execute("""
        INSERT INTO gallery (tryon_id, image_path, tanjak_id)
        VALUES (?,?,?)
    """, (tryon_id, image_path, tanjak_id))
    conn.commit()
    conn.close()

def get_gallery(limit=12):
    conn = get_connection()
    rows = conn.execute("""
        SELECT g.*, t.name as tanjak_name
        FROM gallery g LEFT JOIN tanjak t ON g.tanjak_id = t.id
        WHERE g.is_public=1
        ORDER BY g.created_at DESC LIMIT ?
    """, (limit,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_stats():
    conn = get_connection()
    stats = {
        "total_tryon": conn.execute("SELECT COUNT(*) FROM tryon_history").fetchone()[0],
        "total_tanjak": conn.execute("SELECT COUNT(*) FROM tanjak WHERE is_active=1").fetchone()[0],
        "total_umkm": conn.execute("SELECT COUNT(*) FROM umkm").fetchone()[0],
        "total_gallery": conn.execute("SELECT COUNT(*) FROM gallery WHERE is_public=1").fetchone()[0],
    }
    conn.close()
    return stats


# ── CRUD operations for Admin Dashboard ───────────────────

def get_all_tanjak_admin():
    conn = get_connection()
    rows = conn.execute("SELECT * FROM tanjak ORDER BY sort_order").fetchall()
    conn.close()
    return [dict(r) for r in rows]

def add_tanjak(tid, name, file_name, scale, v_offset, philosophy, origin, usage, price, artisan, artisan_wa, commission):
    conn = get_connection()
    conn.execute("""
        INSERT INTO tanjak (id, name, file, scale, v_offset, philosophy, origin, usage, price, artisan, artisan_wa, commission, is_active)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
    """, (tid, name, file_name, scale, v_offset, philosophy, origin, usage, price, artisan, artisan_wa, commission))
    conn.commit()
    conn.close()

def update_tanjak(tid, name, file_name, scale, v_offset, philosophy, origin, usage, price, artisan, artisan_wa, commission, is_active=1):
    conn = get_connection()
    conn.execute("""
        UPDATE tanjak
        SET name=?, file=?, scale=?, v_offset=?, philosophy=?, origin=?, usage=?, price=?, artisan=?, artisan_wa=?, commission=?, is_active=?
        WHERE id=?
    """, (name, file_name, scale, v_offset, philosophy, origin, usage, price, artisan, artisan_wa, commission, is_active, tid))
    conn.commit()
    conn.close()

def delete_tanjak(tid):
    conn = get_connection()
    # Soft delete to prevent constraint violation on historical tryons/umkms
    conn.execute("UPDATE tanjak SET is_active=0 WHERE id=?", (tid,))
    conn.commit()
    conn.close()

def add_umkm(artisan, location, phone, whatsapp, description, rating, total_sold, tanjak_id):
    conn = get_connection()
    conn.execute("""
        INSERT INTO umkm (artisan, location, phone, whatsapp, description, rating, total_sold, tanjak_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (artisan, location, phone, whatsapp, description, rating, total_sold, tanjak_id))
    conn.commit()
    conn.close()

def update_umkm(umkm_id, artisan, location, phone, whatsapp, description, rating, total_sold, tanjak_id):
    conn = get_connection()
    conn.execute("""
        UPDATE umkm
        SET artisan=?, location=?, phone=?, whatsapp=?, description=?, rating=?, total_sold=?, tanjak_id=?
        WHERE id=?
    """, (artisan, location, phone, whatsapp, description, rating, total_sold, tanjak_id, umkm_id))
    conn.commit()
    conn.close()

def delete_umkm(umkm_id):
    conn = get_connection()
    conn.execute("DELETE FROM umkm WHERE id=?", (umkm_id,))
    conn.commit()
    conn.close()


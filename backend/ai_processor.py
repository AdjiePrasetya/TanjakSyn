"""
backend/ai_processor.py
Modul AI untuk pemasangan tanjak menggunakan MediaPipe Face Mesh

Fitur:
  1. Validasi arah wajah  – Menolak wajah yang tidak menghadap lurus (yaw/roll).
  2. Remove background    – Menghapus latar belakang menggunakan rembg jika tersedia, dengan GrabCut sebagai fallback.
  3. Auto-crop portrait   – Memotong area kepala sampai perut dengan rasio aspek 4:5.
  4. Pasang tanjak        – Melakukan transformasi perspektif (perspective warp) tanjak ke kepala berdasarkan landmark wajah.
"""

import cv2
import mediapipe as mp
import numpy as np
import math
import base64
import time
import logging

# Inisialisasi logger untuk melacak jalannya pipeline pemrosesan citra
logger = logging.getLogger(__name__)

# ── INSTANSIASI MEDIAPIPE FACE MESH ──────────────────────────────────────────────────
# Menggunakan model Face Mesh dari Google MediaPipe untuk memetakan 468+ landmark wajah 3D.
_mp_face_mesh = mp.solutions.face_mesh
_face_mesh = _mp_face_mesh.FaceMesh(
    static_image_mode=True,       # Mode gambar statis (bukan video stream) untuk akurasi optimal.
    max_num_faces=1,             # Hanya memproses 1 wajah utama untuk performa virtual try-on.
    refine_landmarks=True,       # Mengaktifkan landmark tambahan yang detail di sekitar mata, bibir, dan pupil.
    min_detection_confidence=0.3, # Ambang batas minimum kepercayaan deteksi wajah.
)

# ── OPERASI REMBG (PENGHAPUSAN LATAR BELAKANG OTOMATIS) ────────────────────────────
# rembg adalah pustaka berbasis model AI U-2-Net untuk segmentasi latar belakang yang sangat rapi.
# Jika pustaka rembg tidak terpasang di sistem, sistem akan mendeteksi ImportError dan beralih ke GrabCut.
try:
    from rembg import remove as _rembg_remove
    _HAS_REMBG = True
except ImportError:
    _HAS_REMBG = False

# Parameter ambang batas toleransi arah wajah (Face Orientation Validation Thresholds)
_YAW_THRESHOLD  = 0.12   # Toleransi simpangan hadap kiri/kanan (rasio hidung terhadap lebar wajah).
_ROLL_THRESHOLD = 25.0   # Toleransi sudut kemiringan kepala (derajat rotasi roll).


# ════════════════════════════════════════════════════════════════════════════════════
# FUNGSI PEMBANTU: FORMAT KONVERSI
# ════════════════════════════════════════════════════════════════════════════════════

def _ensure_bgra(img: np.ndarray) -> np.ndarray:
    """
    Memastikan citra memiliki 4 saluran warna (Blue, Green, Red, Alpha / BGRA).
    
    Saluran Alpha (transparansi) sangat penting untuk menumpuk gambar tanjak 
    dan hasil potong tubuh tanpa latar belakang.
    
    Args:
        img (np.ndarray): Citra input (skala abu-abu, BGR, atau BGRA).
        
    Returns:
        np.ndarray: Citra terkonversi dalam format BGRA.
    """
    if img.ndim == 2:
        return cv2.cvtColor(img, cv2.COLOR_GRAY2BGRA)
    if img.shape[2] == 3:
        return cv2.cvtColor(img, cv2.COLOR_BGR2BGRA)
    return img


def _bgra_to_bgr_white(img: np.ndarray) -> np.ndarray:
    """
    Menggabungkan citra ber-saluran transparansi (BGRA) ke atas latar belakang putih solid (BGR).
    
    Hal ini diperlukan karena MediaPipe Face Mesh membutuhkan kontras warna BGR 3 saluran 
    tanpa transparansi agar algoritma deteksi wajahnya bekerja optimal.
    
    Args:
        img (np.ndarray): Citra input dalam format BGRA.
        
    Returns:
        np.ndarray: Citra 3-saluran (BGR) berlatar belakang putih.
    """
    if img.ndim == 3 and img.shape[2] == 4:
        alpha = img[:, :, 3:4].astype(np.float32) / 255.0
        rgb   = img[:, :, :3].astype(np.float32)
        white = np.full_like(rgb, 255.0)
        # Rumus blending: C_out = C_src * alpha + C_bg * (1 - alpha)
        out   = (rgb * alpha + white * (1.0 - alpha)).astype(np.uint8)
        return out
    if img.ndim == 3 and img.shape[2] == 4:
        return img[:, :, :3]
    return img


def make_bg_white(img):
    """
    Fungsi alias usang (legacy) untuk mempertahankan kompatibilitas dengan pemanggil eksternal lama
    yang membutuhkan konversi warna latar belakang putih.
    """
    return _bgra_to_bgr_white(img)


# ════════════════════════════════════════════════════════════════════════════════════
# 1. VALIDASI ARAH WAJAH (FACE DIRECTION VALIDATION)
# ════════════════════════════════════════════════════════════════════════════════════

def check_face_direction(landmarks, img_w: int, img_h: int) -> dict:
    """
    Memeriksa apakah posisi wajah pada foto menghadap lurus ke depan (frontal).
    
    Validasi ini menegakkan dua kondisi demi hasil fitting tanjak yang realistis:
    1. Yaw (Hadap Kiri/Kanan): Dihitung dengan membandingkan rasio jarak hidung (landmark 1)
       terhadap tepi kiri wajah (landmark 234) dan tepi kanan wajah (landmark 454).
    2. Roll (Kemiringan): Dihitung berdasarkan sudut trigonometri atan2 antara 
       sudut luar mata kiri (landmark 33) dan mata kanan (landmark 263).
       
    Args:
        landmarks: Kumpulan objek koordinat landmark wajah dari MediaPipe.
        img_w (int): Lebar piksel citra asli.
        img_h (int): Tinggi piksel citra asli.
        
    Returns:
        dict: Hasil validasi berupa struktur:
            {
               "ok": bool,        # True jika wajah lolos syarat kemiringan & sudut hadap.
               "reason": str|None,# Penjelasan dalam bahasa Indonesia jika ditolak.
               "yaw_ratio": float,# Nilai rasio yaw (makin dekat 0, makin simetris lurus).
               "roll_deg": float  # Sudut kemiringan kepala dalam derajat.
            }
    """
    left_x  = landmarks[234].x
    right_x = landmarks[454].x
    nose_x  = landmarks[1].x
    face_w  = right_x - left_x

    # Mencegah pembagian dengan nol jika terdeteksi data wajah rusak
    if face_w < 1e-6:
        return {"ok": False, "reason": "Wajah tidak terdeteksi dengan jelas.", "yaw_ratio": 0, "roll_deg": 0}

    # Menghitung titik tengah hipotesis lebar wajah
    face_center_x = (left_x + right_x) / 2.0
    # Deviasi hidung dari titik tengah wajah. Positif = hadap kanan, Negatif = hadap kiri.
    yaw_ratio = (nose_x - face_center_x) / face_w

    # Menghitung derajat kemiringan mata terhadap sumbu horizontal (Roll)
    lx = landmarks[33].x  * img_w;  ly = landmarks[33].y  * img_h
    rx = landmarks[263].x * img_w;  ry = landmarks[263].y * img_h
    roll_deg = abs(math.degrees(math.atan2(ry - ly, rx - lx)))
    if roll_deg > 90:
        roll_deg = 180 - roll_deg

    result = {"ok": True, "reason": None,
              "yaw_ratio": round(yaw_ratio, 3), "roll_deg": round(roll_deg, 1)}

    # Melakukan evaluasi berdasarkan parameter threshold yang telah ditentukan
    if abs(yaw_ratio) > _YAW_THRESHOLD:
        arah = "kanan" if yaw_ratio > 0 else "kiri"
        result["ok"] = False
        result["reason"] = (
            f"Wajah terdeteksi menghadap ke {arah}. "
            "Gunakan foto dengan wajah menghadap lurus ke depan agar "
            "tanjak dapat terpasang dengan sempurna."
        )
    elif roll_deg > _ROLL_THRESHOLD:
        result["ok"] = False
        result["reason"] = (
            f"Kepala terdeteksi miring {roll_deg:.0f}\u00b0. "
            "Gunakan foto dengan kepala tegak lurus ke depan."
        )

    return result


# ════════════════════════════════════════════════════════════════════════════════════
# 2. PENGHAPUSAN LATAR BELAKANG (BACKGROUND REMOVAL)
# ════════════════════════════════════════════════════════════════════════════════════

def _remove_bg_rembg(img_bgr: np.ndarray) -> np.ndarray:
    """
    Penghapusan latar belakang tingkat lanjut menggunakan modul AI 'rembg'.
    
    Proses:
    1. Mengubah format NumPy array BGR OpenCV ke format RGB PIL Image.
    2. Menjalankan model deep learning untuk mengekstrak subjek utama (orang).
    3. Mengembalikan citra dalam format BGRA dengan saluran transparansi (alpha channel) yang halus.
    
    Args:
        img_bgr (np.ndarray): Citra input 3-saluran BGR.
        
    Returns:
        np.ndarray: Citra hasil segmentasi format 4-saluran BGRA.
    """
    import io
    from PIL import Image
    pil_img = Image.fromarray(cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB))
    buf = io.BytesIO()
    pil_img.save(buf, format="PNG")
    buf.seek(0)
    result_bytes = _rembg_remove(buf.read())
    pil_result = Image.open(io.BytesIO(result_bytes)).convert("RGBA")
    return cv2.cvtColor(np.array(pil_result), cv2.COLOR_RGBA2BGRA)


def _remove_bg_grabcut(img_bgr: np.ndarray) -> np.ndarray:
    """
    Metode fallback penghapusan latar belakang tradisional menggunakan algoritma OpenCV GrabCut.
    
    Algoritma ini menggunakan inisialisasi kotak pembatas (bounding box) otomatis
    yang mencakup 90% area tengah gambar untuk memisahkan latar depan (subjek) 
    dari latar belakang secara iteratif (5 kali perulangan).
    
    Args:
        img_bgr (np.ndarray): Citra input 3-saluran BGR.
        
    Returns:
        np.ndarray: Citra BGRA dengan background hitam transparan pada tepi subjek yang diperhalus Gaussian.
    """
    h, w = img_bgr.shape[:2]
    mask = np.zeros((h, w), np.uint8)
    mx, my = max(1, int(w * 0.05)), max(1, int(h * 0.05))
    # Kotak pembatas (x, y, w, h) menyisakan 5% margin luar
    rect = (mx, my, w - 2 * mx, h - 2 * my)
    bgd = np.zeros((1, 65), np.float64)
    fgd = np.zeros((1, 65), np.float64)
    try:
        cv2.grabCut(img_bgr, mask, rect, bgd, fgd, 5, cv2.GC_INIT_WITH_RECT)
        # Menandai piksel yang diyakini/pasti merupakan latar depan
        fg = np.where((mask == cv2.GC_FGD) | (mask == cv2.GC_PR_FGD), 255, 0).astype(np.uint8)
        # Melakukan operasi morfologi tutup dan buka untuk merapikan lubang kecil dalam masker subjek
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        fg = cv2.morphologyEx(fg, cv2.MORPH_CLOSE, kernel, iterations=2)
        fg = cv2.morphologyEx(fg, cv2.MORPH_OPEN,  kernel, iterations=1)
        # Memberikan efek blur gaussian lembut pada masker luar untuk memperhalus tepian rambut
        fg = cv2.GaussianBlur(fg, (5, 5), 0)
    except Exception:
        # Jika algoritma grabcut mengalami error matematis, gunakan masker putih menyeluruh (fallback)
        fg = np.full((h, w), 255, dtype=np.uint8)
    bgra = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2BGRA)
    bgra[:, :, 3] = fg
    return bgra


def remove_background(img_bgr: np.ndarray) -> np.ndarray:
    """
    Fungsi orkestrator pemotong latar belakang utama dengan strategi bertingkat (fallback).
    Mendahulukan kecerdasan buatan 'rembg' dan beralih ke OpenCV GrabCut jika rembg absen.
    
    Args:
        img_bgr (np.ndarray): Citra input 3-saluran.
        
    Returns:
        np.ndarray: Citra transparan BGRA.
    """
    if _HAS_REMBG:
        try:
            return _remove_bg_rembg(img_bgr)
        except Exception as e:
            logger.warning(f"rembg error: {e} — fallback GrabCut")
    return _remove_bg_grabcut(img_bgr)


# ════════════════════════════════════════════════════════════════════════════════════
# 3. PEMOTONGAN PORTRAIT OTOMATIS (AUTO-CROP PORTRAIT)
# ════════════════════════════════════════════════════════════════════════════════════

def auto_crop_portrait(img_bgra: np.ndarray,
                       landmarks=None,
                       img_h: int = None,
                       img_w: int = None) -> np.ndarray:
    """
    Memotong gambar secara cerdas agar berfokus pada area potret kepala hingga dada/perut 
    dengan rasio aspek ideal 4:5 (rasio standar mobile UI & Instagram).
    
    Metode:
    - Metode 1 (Landmarks): Menggunakan koordinat landmark ubun-ubun kepala (10), 
      dagu bawah (152), pipi kiri (234), dan pipi kanan (454) sebagai patokan pembingkaian.
    - Metode 2 (Bbox Tanpa Landmark): Menganalisis piksel aktif pada saluran alpha (nilai > 10)
      untuk memotong ruang kosong (padding) yang berlebihan secara dinamis.
      
    Setelah pembatasan selesai, dilakukan penambahan border transparan (padding) 
    agar potongan gambar presisi memenuhi rasio aspek target 4:5 tanpa meregangkan gambar.
    
    Args:
        img_bgra (np.ndarray): Citra input transparan format BGRA.
        landmarks: Koordinat landmark dari detektor MediaPipe Face Mesh.
        img_h (int, optional): Tinggi piksel gambar asli.
        img_w (int, optional): Lebar piksel gambar asli.
        
    Returns:
        np.ndarray: Citra berformat BGRA yang telah dipotong dan disesuaikan ke rasio 4:5.
    """
    h, w = img_bgra.shape[:2]

    if landmarks is not None and img_h and img_w:
        # Menghitung koordinat piksel jangkar wajah
        top_y    = int(landmarks[10].y  * img_h)
        bottom_y = int(landmarks[152].y * img_h)
        left_x   = int(landmarks[234].x * img_w)
        right_x  = int(landmarks[454].x * img_w)

        face_h = max(bottom_y - top_y, 1)
        face_w = max(right_x - left_x, 1)

        # Menentukan margin ruang atas (untuk menaruh mahkota tanjak) dan area tubuh bawah (perut)
        y1 = max(0, top_y    - int(face_h * 0.7))
        y2 = min(h, bottom_y + int(face_h * 2.4))
        x1 = max(0, left_x  - int(face_w * 0.55))
        x2 = min(w, right_x + int(face_w * 0.55))
    else:
        # Deteksi berbasis bounding box piksel aktif (jika deteksi landmark tidak ada)
        alpha = img_bgra[:, :, 3] if img_bgra.shape[2] == 4 else np.full((h, w), 255, np.uint8)
        rows  = np.any(alpha > 10, axis=1)
        cols  = np.any(alpha > 10, axis=0)
        if rows.any():
            rmin, rmax = np.where(rows)[0][[0, -1]]
            cmin, cmax = np.where(cols)[0][[0, -1]]
            subj_h = rmax - rmin
            subj_w = cmax - cmin
            y1 = rmin
            y2 = min(h, rmin + int(subj_h * 0.70))
            x1 = max(0, cmin - int(subj_w * 0.05))
            x2 = min(w, cmax + int(subj_w * 0.05))
        else:
            y1, x1, y2, x2 = 0, 0, h, w

    # Validasi dimensi hasil kalkulasi potong agar tidak menghasilkan citra kosong
    if y2 - y1 < 10 or x2 - x1 < 10:
        return img_bgra

    cropped = img_bgra[y1:y2, x1:x2].copy()
    ch, cw  = cropped.shape[:2]

    # Penyelarasan rasio aspek ke 4:5 (Lebar : Tinggi)
    target_ratio = 4.0 / 5.0
    curr_ratio   = cw / max(ch, 1)

    if curr_ratio > target_ratio:
        # Jika gambar terlalu lebar, berikan padding transparan di bagian atas & bawah
        new_h = int(cw / target_ratio)
        pad   = new_h - ch
        pt, pb = pad // 2, pad - pad // 2
        cropped = cv2.copyMakeBorder(cropped, pt, pb, 0, 0,
                                     cv2.BORDER_CONSTANT, value=(0, 0, 0, 0))
    elif curr_ratio < target_ratio:
        # Jika gambar terlalu tinggi, berikan padding transparan di bagian kiri & kanan
        new_w = int(ch * target_ratio)
        pad   = new_w - cw
        pl, pr = pad // 2, pad - pad // 2
        cropped = cv2.copyMakeBorder(cropped, 0, 0, pl, pr,
                                     cv2.BORDER_CONSTANT, value=(0, 0, 0, 0))

    return cropped


# ════════════════════════════════════════════════════════════════════════════════════
# 4. DETEKSI LANDMARK MULTI-STRATEGI (FACE LANDMARK DETECTION)
# ════════════════════════════════════════════════════════════════════════════════════

def detect_landmarks(img_person: np.ndarray):
    """
    Melakukan deteksi landmark wajah dengan pendekatan 'Multi-Strategy'.
    
    Karena MediaPipe terkadang gagal mendeteksi wajah pada foto portrait utuh (karena jarak
    wajah terlalu jauh), fungsi ini menerapkan 3 strategi deteksi bertahap:
    1. CROP_50: Memotong 50% area atas gambar lalu dianalisis (fokus pada kepala).
    2. FULL_IMG: Menganalisis keseluruhan gambar tanpa modifikasi.
    3. CROP_30: Memotong 30% area atas gambar lalu dianalisis (fokus ekstrim pada wajah).
    
    Jika pemotongan dilakukan, koordinat y hasil deteksi akan dikalibrasi kembali
    ke skala koordinat gambar utuh sebelum dikembalikan.
    
    Args:
        img_person (np.ndarray): Citra input dalam format NumPy array.
        
    Returns:
        tuple: (landmarks, strategy_name) jika deteksi berhasil, atau (None, None) jika gagal.
    """
    orig_h, orig_w = img_person.shape[:2]

    strategies = []
    # Strategi 1: Crop area 50% bagian atas
    crop50_h = int(orig_h * 0.50)
    crop50   = img_person[0:crop50_h, :]
    if crop50.size > 0:
        strategies.append(("CROP_50", _bgra_to_bgr_white(crop50), crop50_h, orig_h))
        
    # Strategi 2: Analisis gambar penuh
    strategies.append(("FULL_IMG", _bgra_to_bgr_white(img_person), orig_h, orig_h))
    
    # Strategi 3: Crop area 30% bagian atas (ekstrim close-up)
    crop30_h = int(orig_h * 0.30)
    crop30   = img_person[0:crop30_h, :]
    if crop30.size > 0:
        strategies.append(("CROP_30", _bgra_to_bgr_white(crop30), crop30_h, orig_h))

    # Mengeksekusi strategi satu per satu sampai deteksi sukses
    for name, img_check, check_h, total_h in strategies:
        if img_check is None or img_check.size == 0:
            continue
        img_rgb = cv2.cvtColor(img_check, cv2.COLOR_BGR2RGB)
        results = _face_mesh.process(img_rgb)
        if results.multi_face_landmarks:
            lms = results.multi_face_landmarks[0].landmark
            # Rekalibrasi nilai ordinat (y) agar sesuai dimensi gambar asli
            if name in ("CROP_50", "CROP_30"):
                for lm in lms:
                    lm.y = (lm.y * check_h) / total_h
            return lms, name

    return None, None


# ════════════════════════════════════════════════════════════════════════════════════
# 5. PEMASANGAN TANJAK (PERSPECTIVE WARPING & ASSEMBLY)
# ════════════════════════════════════════════════════════════════════════════════════

def calculate_head_target_points(landmarks, img_w, img_h, tanjak_ratio, scale, v_offset):
    """
    Menghitung 4 titik jangkar tujuan (Top-Left, Top-Right, Bottom-Left, Bottom-Right)
    pada area dahi kepala subjek sebagai koordinat proyeksi penempelan tanjak.
    
    Fungsi ini melakukan kalkulasi geometri kompleks:
    1. Mengukur kemiringan kepala (sudut rotasi roll) berdasarkan vektor mata kiri ke kanan.
    2. Menghitung proyeksi lebar tanjak disesuaikan parameter skala (scale) dan lebar wajah.
    3. Mengkalkulasi tinggi tanjak proporsional berdasarkan rasio aspek aset tanjak asli.
    4. Menentukan titik bawah tengah tanjak di dahi berdasarkan pergeseran offset vertikal (v_offset).
    5. Membuat matriks 4 titik jangkar yang berputar selaras dengan sudut kemiringan kepala.
    
    Args:
        landmarks: Objek koordinat wajah MediaPipe.
        img_w (int): Lebar area gambar tujuan.
        img_h (int): Tinggi area gambar tujuan.
        tanjak_ratio (float): Aspek rasio tinggi/lebar dari gambar aset tanjak asli.
        scale (float): Pengali ukuran tanjak.
        v_offset (float): Pengali pergeseran vertikal tanjak pada kepala.
        
    Returns:
        np.float32: Array berdimensi 4x2 yang mewakili koordinat (x,y) dari 4 titik tujuan.
    """
    # Mengambil koordinat tepi pelipis kiri, pelipis kanan, dan dahi tengah atas
    pt_left     = np.array([landmarks[234].x * img_w, landmarks[234].y * img_h])
    pt_right    = np.array([landmarks[454].x * img_w, landmarks[454].y * img_h])
    pt_forehead = np.array([landmarks[10].x  * img_w, landmarks[10].y  * img_h])

    # Vektor garis pelipis mata & perhitungan lebar wajah
    vec_eye    = pt_right - pt_left
    face_width = np.linalg.norm(vec_eye)
    angle      = np.arctan2(vec_eye[1], vec_eye[0]) # Sudut rotasi kepala dalam radian

    # Ukuran tanjak dinamis
    tanjak_w = face_width * scale
    tanjak_h = tanjak_w * tanjak_ratio

    # Vektor arah tegak lurus (ke atas) dan sejajar (ke kanan) dari kepala yang miring
    up_vec    = np.array([ math.sin(angle), -math.cos(angle)])
    right_vec = np.array([ math.cos(angle),  math.sin(angle)])

    # Titik tengah tepi bawah tanjak yang bergeser sejauh offset vertikal
    center_bottom = pt_forehead + (-up_vec * (tanjak_h * v_offset))
    half_w = tanjak_w / 2

    # Melakukan rotasi titik sudut luar tanjak berdasarkan orientasi kemiringan kepala
    bl = center_bottom - (right_vec * half_w)
    br = center_bottom + (right_vec * half_w)
    tl = bl + (up_vec * tanjak_h)
    tr = br + (up_vec * tanjak_h)

    return np.float32([tl, tr, bl, br])


def create_placeholder_tanjak():
    """
    Membuat aset tanjak tiruan (placeholder) berbentuk segitiga ornamen bernuansa emas/maroon
    menggunakan fungsi gambar primitif OpenCV, apabila berkas gambar aset tanjak asli hilang.
    
    Returns:
        np.ndarray: Citra placeholder format BGRA berukuran 320x200 piksel.
    """
    h, w = 200, 320
    img = np.zeros((h, w, 4), dtype=np.uint8)
    pts = np.array([[w // 2, 5], [w - 10, h - 10], [10, h - 10]], np.int32)
    # Mengisi warna maroon pada isi segitiga
    cv2.fillPoly(img[:, :, :3], [pts], (20, 10, 100))
    # Memberi transparansi penuh pada area luar segitiga, dan solid di dalam segitiga
    cv2.fillPoly(img[:, :, 3:4], [pts], (255,))
    # Menggambar outline berwarna emas terang
    cv2.polylines(img[:, :, :3], [pts], True, (0, 180, 220), 3)
    return img


# ════════════════════════════════════════════════════════════════════════════════════
# ANTARMUKA API UTAMA (MAIN PUBLIC API PIPELINE)
# ════════════════════════════════════════════════════════════════════════════════════

def process_tryon(person_bytes: bytes, tanjak_bytes: bytes,
                  scale: float = 2.6, v_offset: float = 0.35):
    """
    Pipeline lengkap orkestrasi Virtual Try-On Tanjak berbasis AI.
    
    Tahapan Eksekusi:
      1. Decode byte masukan foto pengguna dan aset gambar tanjak.
      2. Deteksi wajah pertama menggunakan Face Mesh multi-strategi pada foto asli.
      3. Validasi kemiringan wajah & hadap wajah (menolak wajah menyamping).
      4. Hapus latar belakang foto pengguna (segmentasi AI).
      5. Pangkas area foto menjadi rasio potret terfokus (kepala hingga dada) dengan aspek 4:5.
      6. Lakukan deteksi ulang Face Mesh pada gambar hasil pemotongan untuk akurasi presisi tinggi.
      7. Hitung matriks proyeksi perspektif 4 titik sudut, lakukan warpPerspective pada gambar tanjak.
      8. Lakukan blending / penumpukan gambar tanjak di atas kepala subjek menggunakan logika masking alpha.
      
    Args:
        person_bytes (bytes): Data biner citra potret pengguna (PNG/JPG).
        tanjak_bytes (bytes): Data biner citra ornamen tanjak berlatar transparan (PNG).
        scale (float, optional): Parameter skala ukuran tanjak. Default 2.6.
        v_offset (float, optional): Parameter pergeseran vertikal tanjak. Default 0.35.
        
    Returns:
        tuple: (png_bytes, info_dict)
            - png_bytes (bytes): Data biner file citra hasil pemasangan tanjak berformat PNG.
            - info_dict (dict): Metadata hasil pemrosesan (kecepatan, sudut wajah, strategi).
            
    Raises:
        ValueError: Jika gambar rusak, wajah tidak terdeteksi, atau foto melanggar aturan validasi arah wajah.
    """
    t0 = time.time()

    # ── 1. DECODE CITRA PENGGUNA ──────────────────────────────────────────────────────
    pa = np.frombuffer(person_bytes, np.uint8)
    img_orig = cv2.imdecode(pa, cv2.IMREAD_UNCHANGED)
    if img_orig is None:
        raise ValueError("Gambar tidak dapat dibaca. Pastikan format file benar (JPG/PNG).")

    # Standardisasi format input ke format 3-saluran BGR
    if img_orig.ndim == 2:
        img_bgr = cv2.cvtColor(img_orig, cv2.COLOR_GRAY2BGR)
    elif img_orig.shape[2] == 4:
        img_bgr = cv2.cvtColor(img_orig, cv2.COLOR_BGRA2BGR)
    else:
        img_bgr = img_orig.copy()

    orig_h, orig_w = img_bgr.shape[:2]

    # ── 2. DECODE GAMBAR ASET TANJAK ──────────────────────────────────────────────────
    img_tanjak = None
    if tanjak_bytes:
        ta = np.frombuffer(tanjak_bytes, np.uint8)
        img_tanjak = cv2.imdecode(ta, cv2.IMREAD_UNCHANGED)
    if img_tanjak is None:
        img_tanjak = create_placeholder_tanjak()
    img_tanjak = _ensure_bgra(img_tanjak)

    # ── 3. DETEKSI AWAL WAJAH & VALIDASI ORIENTASI ──────────────────────────────────
    img_bgra_orig = _ensure_bgra(img_bgr)
    landmarks_init, strat_init = detect_landmarks(img_bgra_orig)

    if landmarks_init is None:
        raise ValueError(
            "Wajah tidak terdeteksi. "
            "Pastikan wajah terlihat jelas, pencahayaan cukup, dan foto tidak buram."
        )

    # Memastikan wajah lurus frontal demi estetika tanjak
    face_check = check_face_direction(landmarks_init, orig_w, orig_h)
    if not face_check["ok"]:
        raise ValueError(face_check["reason"])

    # ── 4. SEGMENTASI & PENGHAPUSAN BACKROUND ─────────────────────────────────────────
    img_nobg = remove_background(img_bgr)   # Menghasilkan citra berformat BGRA

    # ── 5. PEMOTONGAN PORTRAIT 4:5 ────────────────────────────────────────────────────
    img_cropped = auto_crop_portrait(
        img_nobg,
        landmarks=landmarks_init,
        img_h=orig_h,
        img_w=orig_w,
    )

    # ── 6. DETEKSI ULANG LANDMARK DI GAMBAR BARU (CROP) ───────────────────────────────
    crop_h, crop_w = img_cropped.shape[:2]
    landmarks, strategy = detect_landmarks(img_cropped)

    if landmarks is None:
        # Fallback: Gunakan koordinat inisial dan gambar penuh jika pemotongan mengacaukan Face Mesh
        img_final = img_nobg
        landmarks = landmarks_init
        strategy  = strat_init + "_FALLBACK"
        fin_h, fin_w = img_nobg.shape[:2]
    else:
        img_final = img_cropped
        fin_h, fin_w = crop_h, crop_w

    # ── 7. PROYEKSI HOMOGRAFI PERSPEKTIF TANJAK ───────────────────────────────────────
    h_tj, w_tj   = img_tanjak.shape[:2]
    tanjak_ratio = h_tj / w_tj
    # Titik sudut asal dari gambar datar tanjak
    src_pts = np.float32([[0, 0], [w_tj, 0], [0, h_tj], [w_tj, h_tj]])
    # Menghitung posisi 4 titik jangkar di atas kepala miring subjek
    dst_pts = calculate_head_target_points(landmarks, fin_w, fin_h,
                                            tanjak_ratio, scale, v_offset)

    # Menghitung matriks transformasi perspektif homografi (3x3)
    matrix = cv2.getPerspectiveTransform(src_pts, dst_pts)
    # Melakukan pembengkokan gambar tanjak ke koordinat kepala tujuan
    warped = cv2.warpPerspective(img_tanjak, matrix, (fin_w, fin_h),
                                  flags=cv2.INTER_LINEAR,
                                  borderMode=cv2.BORDER_CONSTANT,
                                  borderValue=(0, 0, 0, 0))

    # ── 8. BLENDING GAMBAR DENGAN MASKING ALPHA TRANSPARAN ────────────────────────────
    alpha     = warped[:, :, 3] / 255.0
    alpha_inv = 1.0 - alpha
    final     = img_final.copy()

    # Operasi blending per saluran warna RGB
    for c in range(3):
        final[:, :, c] = (alpha * warped[:, :, c] + alpha_inv * final[:, :, c]).astype(np.uint8)
    # Menetapkan nilai transparansi alpha gabungan akhir
    final[:, :, 3] = np.maximum(final[:, :, 3], warped[:, :, 3])

    # ── 9. ENKODE HASIL KE FORMAT PNG BINARY ──────────────────────────────────────────
    ok, buf = cv2.imencode('.png', final)
    if not ok:
        raise ValueError("Gagal mengenkode gambar hasil.")

    proc_time = round(time.time() - t0, 2)

    return buf.tobytes(), {
        "strategy":      strategy,
        "proc_time":     proc_time,
        "original_size": [orig_w, orig_h],
        "output_size":   [fin_w, fin_h],
        "bg_removed":    True,
        "face_yaw":      face_check["yaw_ratio"],
        "face_roll":     face_check["roll_deg"],
    }


def bytes_to_b64(b: bytes, mime: str = "image/png") -> str:
    """
    Mengonversi data citra biner ke string representasi Base64 Data URL.
    
    Sangat berguna untuk mengirimkan file gambar hasil langsung di dalam response JSON 
    untuk langsung ditampilkan di tag <img> src pada frontend HTML.
    
    Args:
        b (bytes): Data biner citra.
        mime (str, optional): Mime type gambar. Default "image/png".
        
    Returns:
        str: String Data URL terformat base64.
    """
    return f"data:{mime};base64," + base64.b64encode(b).decode()

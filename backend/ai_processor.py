"""
backend/ai_processor.py
Modul AI untuk pemasangan tanjak menggunakan MediaPipe Face Mesh

Fitur:
  1. Validasi arah wajah  – tolak wajah tidak frontal (yaw/roll)
  2. Remove background    – rembg jika tersedia, fallback GrabCut
  3. Auto-crop portrait   – potong area kepala sampai perut
  4. Pasang tanjak        – perspective warp ke kepala
"""

import cv2
import mediapipe as mp
import numpy as np
import math
import base64
import time
import logging

logger = logging.getLogger(__name__)

# ── MediaPipe ────────────────────────────────────────────────
_mp_face_mesh = mp.solutions.face_mesh
_face_mesh = _mp_face_mesh.FaceMesh(
    static_image_mode=True,
    max_num_faces=1,
    refine_landmarks=True,
    min_detection_confidence=0.3,
)

# ── rembg (opsional) ────────────────────────────────────────
try:
    from rembg import remove as _rembg_remove
    _HAS_REMBG = True
except ImportError:
    _HAS_REMBG = False

# Threshold validasi arah wajah
_YAW_THRESHOLD  = 0.12   # rasio hidung vs tengah wajah
_ROLL_THRESHOLD = 25.0   # derajat kemiringan kepala


# ════════════════════════════════════════════════════════════
# UTIL: FORMAT KONVERSI
# ════════════════════════════════════════════════════════════

def _ensure_bgra(img: np.ndarray) -> np.ndarray:
    if img.ndim == 2:
        return cv2.cvtColor(img, cv2.COLOR_GRAY2BGRA)
    if img.shape[2] == 3:
        return cv2.cvtColor(img, cv2.COLOR_BGR2BGRA)
    return img

def _bgra_to_bgr_white(img: np.ndarray) -> np.ndarray:
    """Composite BGRA ke BGR dengan background putih (agar MediaPipe bisa deteksi)."""
    if img.ndim == 3 and img.shape[2] == 4:
        alpha = img[:, :, 3:4].astype(np.float32) / 255.0
        rgb   = img[:, :, :3].astype(np.float32)
        white = np.full_like(rgb, 255.0)
        out   = (rgb * alpha + white * (1.0 - alpha)).astype(np.uint8)
        return out
    if img.ndim == 3 and img.shape[2] == 4:
        return img[:, :, :3]
    return img

# Legacy alias (dipanggil jika ada kode lain yang memakai nama lama)
def make_bg_white(img):
    return _bgra_to_bgr_white(img)


# ════════════════════════════════════════════════════════════
# 1. FACE DIRECTION VALIDATION
# ════════════════════════════════════════════════════════════

def check_face_direction(landmarks, img_w: int, img_h: int) -> dict:
    """
    Cek apakah wajah menghadap ke depan (frontal).
    Tolak jika:
      - Yaw  : hidung terlalu ke kiri/kanan dari tengah wajah
      - Roll : kepala terlalu miring

    Returns:
        {"ok": bool, "reason": str|None, "yaw_ratio": float, "roll_deg": float}
    """
    left_x  = landmarks[234].x
    right_x = landmarks[454].x
    nose_x  = landmarks[1].x
    face_w  = right_x - left_x

    if face_w < 1e-6:
        return {"ok": False, "reason": "Wajah tidak terdeteksi dengan jelas.", "yaw_ratio": 0, "roll_deg": 0}

    face_center_x = (left_x + right_x) / 2.0
    yaw_ratio = (nose_x - face_center_x) / face_w

    # Roll: sudut garis antara sudut luar kedua mata
    lx = landmarks[33].x  * img_w;  ly = landmarks[33].y  * img_h
    rx = landmarks[263].x * img_w;  ry = landmarks[263].y * img_h
    roll_deg = abs(math.degrees(math.atan2(ry - ly, rx - lx)))
    if roll_deg > 90:
        roll_deg = 180 - roll_deg

    result = {"ok": True, "reason": None,
              "yaw_ratio": round(yaw_ratio, 3), "roll_deg": round(roll_deg, 1)}

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


# ════════════════════════════════════════════════════════════
# 2. BACKGROUND REMOVAL
# ════════════════════════════════════════════════════════════

def _remove_bg_rembg(img_bgr: np.ndarray) -> np.ndarray:
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
    h, w = img_bgr.shape[:2]
    mask = np.zeros((h, w), np.uint8)
    mx, my = max(1, int(w * 0.05)), max(1, int(h * 0.05))
    rect = (mx, my, w - 2 * mx, h - 2 * my)
    bgd = np.zeros((1, 65), np.float64)
    fgd = np.zeros((1, 65), np.float64)
    try:
        cv2.grabCut(img_bgr, mask, rect, bgd, fgd, 5, cv2.GC_INIT_WITH_RECT)
        fg = np.where((mask == cv2.GC_FGD) | (mask == cv2.GC_PR_FGD), 255, 0).astype(np.uint8)
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        fg = cv2.morphologyEx(fg, cv2.MORPH_CLOSE, kernel, iterations=2)
        fg = cv2.morphologyEx(fg, cv2.MORPH_OPEN,  kernel, iterations=1)
        fg = cv2.GaussianBlur(fg, (5, 5), 0)
    except Exception:
        fg = np.full((h, w), 255, dtype=np.uint8)
    bgra = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2BGRA)
    bgra[:, :, 3] = fg
    return bgra

def remove_background(img_bgr: np.ndarray) -> np.ndarray:
    """Return BGRA dengan background dihapus."""
    if _HAS_REMBG:
        try:
            return _remove_bg_rembg(img_bgr)
        except Exception as e:
            logger.warning(f"rembg error: {e} — fallback GrabCut")
    return _remove_bg_grabcut(img_bgr)


# ════════════════════════════════════════════════════════════
# 3. AUTO-CROP PORTRAIT (kepala – perut)
# ════════════════════════════════════════════════════════════

def auto_crop_portrait(img_bgra: np.ndarray,
                       landmarks=None,
                       img_h: int = None,
                       img_w: int = None) -> np.ndarray:
    """
    Crop ke area portrait kepala-perut dengan rasio 4:5.
    Jika landmarks tersedia, gunakan posisi kepala sebagai anchor.
    """
    h, w = img_bgra.shape[:2]

    if landmarks is not None and img_h and img_w:
        top_y    = int(landmarks[10].y  * img_h)
        bottom_y = int(landmarks[152].y * img_h)
        left_x   = int(landmarks[234].x * img_w)
        right_x  = int(landmarks[454].x * img_w)

        face_h = max(bottom_y - top_y, 1)
        face_w = max(right_x - left_x, 1)

        y1 = max(0, top_y    - int(face_h * 0.7))
        y2 = min(h, bottom_y + int(face_h * 2.4))
        x1 = max(0, left_x  - int(face_w * 0.55))
        x2 = min(w, right_x + int(face_w * 0.55))
    else:
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

    if y2 - y1 < 10 or x2 - x1 < 10:
        return img_bgra

    cropped = img_bgra[y1:y2, x1:x2].copy()
    ch, cw  = cropped.shape[:2]

    # Pad ke rasio 4:5
    target_ratio = 4.0 / 5.0
    curr_ratio   = cw / max(ch, 1)

    if curr_ratio > target_ratio:
        new_h = int(cw / target_ratio)
        pad   = new_h - ch
        pt, pb = pad // 2, pad - pad // 2
        cropped = cv2.copyMakeBorder(cropped, pt, pb, 0, 0,
                                     cv2.BORDER_CONSTANT, value=(0, 0, 0, 0))
    elif curr_ratio < target_ratio:
        new_w = int(ch * target_ratio)
        pad   = new_w - cw
        pl, pr = pad // 2, pad - pad // 2
        cropped = cv2.copyMakeBorder(cropped, 0, 0, pl, pr,
                                     cv2.BORDER_CONSTANT, value=(0, 0, 0, 0))

    return cropped


# ════════════════════════════════════════════════════════════
# 4. FACE LANDMARK DETECTION (multi-strategy)
# ════════════════════════════════════════════════════════════

def detect_landmarks(img_person: np.ndarray):
    """
    Jalankan multi-strategy face landmark detection.
    Return (landmarks, strategy_name) atau (None, None).
    """
    orig_h, orig_w = img_person.shape[:2]

    strategies = []
    # Crop 50% atas
    crop50_h = int(orig_h * 0.50)
    crop50   = img_person[0:crop50_h, :]
    if crop50.size > 0:
        strategies.append(("CROP_50", _bgra_to_bgr_white(crop50), crop50_h, orig_h))
    # Full image
    strategies.append(("FULL_IMG", _bgra_to_bgr_white(img_person), orig_h, orig_h))
    # Crop 30% atas
    crop30_h = int(orig_h * 0.30)
    crop30   = img_person[0:crop30_h, :]
    if crop30.size > 0:
        strategies.append(("CROP_30", _bgra_to_bgr_white(crop30), crop30_h, orig_h))

    for name, img_check, check_h, total_h in strategies:
        if img_check is None or img_check.size == 0:
            continue
        img_rgb = cv2.cvtColor(img_check, cv2.COLOR_BGR2RGB)
        results = _face_mesh.process(img_rgb)
        if results.multi_face_landmarks:
            lms = results.multi_face_landmarks[0].landmark
            if name in ("CROP_50", "CROP_30"):
                for lm in lms:
                    lm.y = (lm.y * check_h) / total_h
            return lms, name

    return None, None


# ════════════════════════════════════════════════════════════
# 5. TANJAK PLACEMENT
# ════════════════════════════════════════════════════════════

def calculate_head_target_points(landmarks, img_w, img_h, tanjak_ratio, scale, v_offset):
    pt_left     = np.array([landmarks[234].x * img_w, landmarks[234].y * img_h])
    pt_right    = np.array([landmarks[454].x * img_w, landmarks[454].y * img_h])
    pt_forehead = np.array([landmarks[10].x  * img_w, landmarks[10].y  * img_h])

    vec_eye    = pt_right - pt_left
    face_width = np.linalg.norm(vec_eye)
    angle      = np.arctan2(vec_eye[1], vec_eye[0])

    tanjak_w = face_width * scale
    tanjak_h = tanjak_w * tanjak_ratio

    up_vec    = np.array([ math.sin(angle), -math.cos(angle)])
    right_vec = np.array([ math.cos(angle),  math.sin(angle)])

    center_bottom = pt_forehead + (-up_vec * (tanjak_h * v_offset))
    half_w = tanjak_w / 2

    bl = center_bottom - (right_vec * half_w)
    br = center_bottom + (right_vec * half_w)
    tl = bl + (up_vec * tanjak_h)
    tr = br + (up_vec * tanjak_h)

    return np.float32([tl, tr, bl, br])


def create_placeholder_tanjak():
    h, w = 200, 320
    img = np.zeros((h, w, 4), dtype=np.uint8)
    pts = np.array([[w // 2, 5], [w - 10, h - 10], [10, h - 10]], np.int32)
    cv2.fillPoly(img[:, :, :3], [pts], (20, 10, 100))
    cv2.fillPoly(img[:, :, 3:4], [pts], (255,))
    cv2.polylines(img[:, :, :3], [pts], True, (0, 180, 220), 3)
    return img


# ════════════════════════════════════════════════════════════
# MAIN PUBLIC API
# ════════════════════════════════════════════════════════════

def process_tryon(person_bytes: bytes, tanjak_bytes: bytes,
                  scale: float = 2.6, v_offset: float = 0.35):
    """
    Pipeline lengkap virtual try-on tanjak.

    Langkah:
      1. Decode gambar
      2. Deteksi wajah di gambar asli
      3. Validasi arah wajah (tolak jika tidak frontal)
      4. Hapus background
      5. Crop portrait (kepala–perut)
      6. Deteksi ulang landmark di gambar crop
      7. Pasang tanjak ke kepala

    Returns:
        (png_bytes, info_dict)  atau raises ValueError
    """
    t0 = time.time()

    # ── Decode person ─────────────────────────────────────────
    pa = np.frombuffer(person_bytes, np.uint8)
    img_orig = cv2.imdecode(pa, cv2.IMREAD_UNCHANGED)
    if img_orig is None:
        raise ValueError("Gambar tidak dapat dibaca. Pastikan format file benar (JPG/PNG).")

    # Konversi ke BGR untuk proses
    if img_orig.ndim == 2:
        img_bgr = cv2.cvtColor(img_orig, cv2.COLOR_GRAY2BGR)
    elif img_orig.shape[2] == 4:
        img_bgr = cv2.cvtColor(img_orig, cv2.COLOR_BGRA2BGR)
    else:
        img_bgr = img_orig.copy()

    orig_h, orig_w = img_bgr.shape[:2]

    # ── Decode tanjak ─────────────────────────────────────────
    img_tanjak = None
    if tanjak_bytes:
        ta = np.frombuffer(tanjak_bytes, np.uint8)
        img_tanjak = cv2.imdecode(ta, cv2.IMREAD_UNCHANGED)
    if img_tanjak is None:
        img_tanjak = create_placeholder_tanjak()
    img_tanjak = _ensure_bgra(img_tanjak)

    # ── Step 1: Deteksi wajah di gambar asli ─────────────────
    img_bgra_orig = _ensure_bgra(img_bgr)
    landmarks_init, strat_init = detect_landmarks(img_bgra_orig)

    if landmarks_init is None:
        raise ValueError(
            "Wajah tidak terdeteksi. "
            "Pastikan wajah terlihat jelas, pencahayaan cukup, dan foto tidak buram."
        )

    # ── Step 2: Validasi arah wajah ──────────────────────────
    face_check = check_face_direction(landmarks_init, orig_w, orig_h)
    if not face_check["ok"]:
        raise ValueError(face_check["reason"])

    # ── Step 3: Hapus background ──────────────────────────────
    img_nobg = remove_background(img_bgr)   # BGRA

    # ── Step 4: Crop portrait ─────────────────────────────────
    img_cropped = auto_crop_portrait(
        img_nobg,
        landmarks=landmarks_init,
        img_h=orig_h,
        img_w=orig_w,
    )

    # ── Step 5: Deteksi ulang landmark di gambar crop ────────
    crop_h, crop_w = img_cropped.shape[:2]
    landmarks, strategy = detect_landmarks(img_cropped)

    if landmarks is None:
        # Fallback: pakai gambar tanpa crop
        img_final = img_nobg
        landmarks = landmarks_init
        strategy  = strat_init + "_FALLBACK"
        fin_h, fin_w = img_nobg.shape[:2]
    else:
        img_final = img_cropped
        fin_h, fin_w = crop_h, crop_w

    # ── Step 6: Pasang tanjak ─────────────────────────────────
    h_tj, w_tj   = img_tanjak.shape[:2]
    tanjak_ratio = h_tj / w_tj
    src_pts = np.float32([[0, 0], [w_tj, 0], [0, h_tj], [w_tj, h_tj]])
    dst_pts = calculate_head_target_points(landmarks, fin_w, fin_h,
                                            tanjak_ratio, scale, v_offset)

    matrix = cv2.getPerspectiveTransform(src_pts, dst_pts)
    warped = cv2.warpPerspective(img_tanjak, matrix, (fin_w, fin_h),
                                  flags=cv2.INTER_LINEAR,
                                  borderMode=cv2.BORDER_CONSTANT,
                                  borderValue=(0, 0, 0, 0))

    alpha     = warped[:, :, 3] / 255.0
    alpha_inv = 1.0 - alpha
    final     = img_final.copy()

    for c in range(3):
        final[:, :, c] = (alpha * warped[:, :, c] + alpha_inv * final[:, :, c]).astype(np.uint8)
    final[:, :, 3] = np.maximum(final[:, :, 3], warped[:, :, 3])

    # ── Encode ────────────────────────────────────────────────
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
    return f"data:{mime};base64," + base64.b64encode(b).decode()

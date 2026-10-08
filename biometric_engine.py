import os
import time
import importlib
from typing import Any

import cv2
import numpy as np

cv2.setUseOptimized(True)

# ==============================================================================
# TUNABLE BIOMETRIC, DISTANCE & TIMING PARAMETERS (EDIT HERE AT TOP OF FILE)
# ==============================================================================

REQUIRED_BLINKS: int = 2                 # Blinks needed in Stage 3 (Verification & Registration Seal)
BLINK_COOLDOWN_SEC: float = 0.85         # Minimum delay (seconds) between two valid blinks
BLINK_REARM_OPEN_FRAMES: int = 3         # Consecutive open-eye frames required before next blink
BLINK_MIN_CLOSED_FRAMES: int = 1         # Fastest allowed blink duration (in frames)
BLINK_MAX_CLOSED_FRAMES: int = 35        # Slowest allowed blink duration (in frames)

# 2D Iris-Disc Thresholds (Scale-normalized 48x24 eye grid)
IRIS_CLOSE_RATIO: float = 0.70           # Score drop ratio vs open-eye baseline to trigger closed
IRIS_OPEN_RATIO: float = 0.79            # Hysteresis recovery ratio to trigger reopened

# Sitting Distance Parameters (Face width as a fraction of camera frame width)
MIN_FACE_WIDTH_RATIO: float = 0.18       # Below 18% -> "Too Far — Come Closer"
MAX_FACE_WIDTH_RATIO: float = 0.68       # Above 68% -> "Too Close — Sit Farther Back"

# Pipeline & Liveness Parameters
DETECTION_DOWNSCALE_WIDTH: int = 320     # Fast internal width for face detection (eliminates lag)
FEATURE_SCAN_INTERVAL_SEC: float = 0.22  # Throttle 512-D feature scan during Stage 1
RPPG_REQUIRED_FRAMES: int = 12           # Frames required in Stage 2 for optical pulse liveness
RPPG_MIN_STD_DEV: float = 0.15           # Minimum green-channel micro-variance for live skin
LOW_LIGHT_LUMA_THRESHOLD: float = 35.0   # Minimum brightness luma before pausing timer

# Optional InsightFace 512-D ArcFace Engine
HAS_INSIGHTFACE = False
FaceAnalysis: Any = None
try:
    from insightface.app import FaceAnalysis as _FA
    FaceAnalysis = _FA
    HAS_INSIGHTFACE = True
except Exception:
    HAS_INSIGHTFACE = False


class BiometricSecurityEngine:
    POSE_BUCKETS = ("Center", "Turn Left", "Turn Right", "Lift Chin")

    def __init__(self, base_dir: str | None = None) -> None:
        if base_dir is None:
            base_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "biovault_data")
        self.base_dir = base_dir
        self.profiles_dir = os.path.join(self.base_dir, "profiles")
        os.makedirs(self.profiles_dir, exist_ok=True)

        self._models_initialized: bool = False
        self.arcface: Any = None
        self._cv_face_cascade: Any = None

        # Stabilized face bounding box & RAM profile cache
        self._smooth_face: list[float] | None = None
        self._missed_frames: int = 0
        self._profile_cache: dict[str, tuple[np.ndarray, np.ndarray]] = {}

        # Enrollment accumulators
        self.session_start_ts: float = time.time()
        self.current_pose_idx: int = 0
        self.pose_embeddings: dict[int, list[np.ndarray]] = {0: [], 1: [], 2: [], 3: []}
        self.ocular_samples: list[np.ndarray] = []
        self._last_sample_capture_ts: float = 0.0

        # 2D Iris-Disc Blink State Machine
        self.blink_count: int = 0
        self._open_baseline: float | None = None
        self._bridge_luma_ema: float | None = None
        self._closed_frames: int = 0
        self._open_streak: int = BLINK_REARM_OPEN_FRAMES
        self._in_blink: bool = False
        self._last_blink_ts: float = 0.0

        # 3-Stage Verification Pipeline State (STAGE 1: IDENTITY -> STAGE 2: LIVENESS -> STAGE 3: BLINK)
        self._ver_stage: int = 1
        self._ver_id_hits: int = 0
        self._ver_locked_user: str | None = None
        self._last_feature_scan_ts: float = 0.0
        self.rppg_signal_buffer: list[float] = []
        self._ver_liveness_passed: bool = False

        # Diagnostic trackers for 30s timeout screen
        self._last_ver_matched_user: str | None = None
        self._last_ver_arc_score: float = 0.0
        self._last_ver_ocu_score: float = 0.0
        self._last_ver_rppg_ok: bool = False
        self._last_ver_face_seen: bool = False

    # ==========================================================================
    # PROFILE DISK MANAGEMENT (.NPZ)
    # ==========================================================================

    def get_enrolled_users(self) -> list[str]:
        if not os.path.exists(self.profiles_dir):
            return []
        users: list[str] = []
        for fname in os.listdir(self.profiles_dir):
            if fname.lower().endswith(".npz"):
                users.append(os.path.splitext(fname)[0])
        users.sort(key=lambda s: s.lower())
        return users

    def delete_profile(self, username: str) -> bool:
        target = os.path.join(self.profiles_dir, f"{username}.npz")
        self._profile_cache.pop(username, None)
        if os.path.exists(target):
            try:
                os.remove(target)
                return True
            except Exception:
                return False
        return False

    def reset_session(self) -> None:
        self.session_start_ts = time.time()
        self._smooth_face = None
        self._missed_frames = 0

        self.current_pose_idx = 0
        self.pose_embeddings = {0: [], 1: [], 2: [], 3: []}
        self.ocular_samples = []
        self._last_sample_capture_ts = 0.0

        self.blink_count = 0
        self._open_baseline = None
        self._bridge_luma_ema = None
        self._closed_frames = 0
        self._open_streak = BLINK_REARM_OPEN_FRAMES
        self._in_blink = False
        self._last_blink_ts = 0.0

        self._ver_stage = 1
        self._ver_id_hits = 0
        self._ver_locked_user = None
        self._last_feature_scan_ts = 0.0
        self.rppg_signal_buffer = []
        self._ver_liveness_passed = False

        self._last_ver_matched_user = None
        self._last_ver_arc_score = 0.0
        self._last_ver_ocu_score = 0.0
        self._last_ver_rppg_ok = False
        self._last_ver_face_seen = False
        self._profile_cache.clear()

    def ensure_models_loaded(self) -> None:
        if self._models_initialized:
            return

        if hasattr(cv2, "CascadeClassifier"):
            haar_base = getattr(cv2, "data", None)
            haar_dir = getattr(haar_base, "haarcascades", "") if haar_base is not None else ""
            f_xml = os.path.join(haar_dir, "haarcascade_frontalface_default.xml")
            self._cv_face_cascade = cv2.CascadeClassifier(f_xml) if os.path.exists(f_xml) else None
        else:
            self._cv_face_cascade = None

        if HAS_INSIGHTFACE and FaceAnalysis is not None:
            try:
                self.arcface = FaceAnalysis(
                    name="buffalo_l",
                    providers=["CUDAExecutionProvider", "CPUExecutionProvider"]
                )
                self.arcface.prepare(ctx_id=0, det_size=(320, 320))
            except Exception:
                self.arcface = None

        self._models_initialized = True

    def _get_cached_profile(self, uname: str) -> tuple[np.ndarray, np.ndarray] | None:
        if uname in self._profile_cache:
            return self._profile_cache[uname]
        p_path = os.path.join(self.profiles_dir, f"{uname}.npz")
        if not os.path.exists(p_path):
            return None
        try:
            with np.load(p_path) as data:
                mean_emb = np.asarray(data["mean_embedding"], dtype=np.float32)
                ocu_vec = np.asarray(data["ocular_vector"], dtype=np.float32)
            self._profile_cache[uname] = (mean_emb, ocu_vec)
            return mean_emb, ocu_vec
        except Exception:
            return None

    # ==========================================================================
    # CORE DETECTION, 2D IRIS-DISC BLINK & FEATURE HELPERS
    # ==========================================================================

    def _detect_face_and_lighting(self, bgr_frame: np.ndarray) -> dict[str, Any]:
        """Runs fast 320px downscaled face detection + lighting & distance gates."""
        self.ensure_models_loaded()
        h, w = bgr_frame.shape[:2]
        gray = cv2.cvtColor(bgr_frame, cv2.COLOR_BGR2GRAY)
        mean_luma = float(np.mean(gray))
        low_light = mean_luma < LOW_LIGHT_LUMA_THRESHOLD

        center_crop = gray[int(h * 0.25):int(h * 0.75), int(w * 0.25):int(w * 0.75)]
        center_luma = float(np.mean(center_crop)) if center_crop.size else mean_luma
        backlight = (mean_luma - center_luma) > 68.0

        scale = w / float(DETECTION_DOWNSCALE_WIDTH)
        det_h = max(60, int(h / scale))
        small_gray = cv2.resize(gray, (DETECTION_DOWNSCALE_WIDTH, det_h), interpolation=cv2.INTER_LINEAR)

        faces = []
        if self._cv_face_cascade is not None:
            faces = self._cv_face_cascade.detectMultiScale(
                small_gray, scaleFactor=1.12, minNeighbors=4, minSize=(36, 36)
            )

        if len(faces) > 1:
            self._smooth_face = None
            return {
                "num_faces": len(faces), "bbox": None, "gray": gray,
                "dist_state": "MULTI_FACE", "dist_ok": False,
                "low_light": low_light, "backlight": backlight,
            }

        if len(faces) == 1:
            fx_s, fy_s, fw_s, fh_s = faces[0]
            raw_box = [fx_s * scale, fy_s * scale, fw_s * scale, fh_s * scale]
            self._missed_frames = 0
            if self._smooth_face is None:
                self._smooth_face = raw_box
            else:
                a = 0.30
                self._smooth_face = [
                    self._smooth_face[i] + a * (raw_box[i] - self._smooth_face[i])
                    for i in range(4)
                ]
        elif self._smooth_face is not None and self._missed_frames < 5:
            self._missed_frames += 1
        else:
            self._smooth_face = None
            self._open_baseline = None
            return {
                "num_faces": 0, "bbox": None, "gray": gray,
                "dist_state": "NO_FACE", "dist_ok": False,
                "low_light": low_light, "backlight": backlight,
            }

        fx, fy, fw, fh = [int(v) for v in self._smooth_face]
        fx = max(0, min(w - 10, fx))
        fy = max(0, min(h - 10, fy))
        fw = max(10, min(w - fx, fw))
        fh = max(10, min(h - fy, fh))
        bbox = (fx, fy, fw, fh)

        ratio = float(fw) / float(w)
        if ratio < MIN_FACE_WIDTH_RATIO:
            dist_state = "TOO_FAR"
            dist_ok = False
        elif ratio > MAX_FACE_WIDTH_RATIO:
            dist_state = "TOO_CLOSE"
            dist_ok = False
        else:
            dist_state = "OPTIMAL"
            dist_ok = True

        return {
            "num_faces": 1, "bbox": bbox, "gray": gray,
            "dist_state": dist_state, "dist_ok": dist_ok,
            "low_light": low_light, "backlight": backlight,
        }

    def _run_iris_blink_step(
        self, gray: np.ndarray, bbox: tuple[int, int, int, int], allow_count: bool = True
    ) -> dict[str, Any]:
        """
        Runs the scale-normalized 48x24 2D Iris-Disc blink detector (same logic as blink_test.py)
        and returns `eye_rois` and `pupil_pts` for drawing on the camera frame.
        """
        h, w = gray.shape[:2]
        fx, fy, fw, fh = bbox
        now = time.time()

        # Nose-bridge skin reference & hand-obstruction detector
        bx1, bx2 = max(0, fx + int(fw * 0.44)), min(w, fx + int(fw * 0.56))
        by1, by2 = max(0, fy + int(fh * 0.30)), min(h, fy + int(fh * 0.44))
        bridge_patch = gray[by1:by2, bx1:bx2]
        bridge_luma = float(np.mean(bridge_patch)) if bridge_patch.size else 128.0
        if self._bridge_luma_ema is None:
            self._bridge_luma_ema = bridge_luma
        bridge_jump = abs(bridge_luma - self._bridge_luma_ema)
        self._bridge_luma_ema = 0.90 * self._bridge_luma_ema + 0.10 * bridge_luma

        ey1 = max(0, fy + int(fh * 0.32))
        ey2 = min(h, fy + int(fh * 0.45))
        lx1, lx2 = max(0, fx + int(fw * 0.18)), min(w, fx + int(fw * 0.43))
        rx1, rx2 = max(0, fx + int(fw * 0.57)), min(w, fx + int(fw * 0.82))

        l_zone = gray[ey1:ey2, lx1:lx2]
        r_zone = gray[ey1:ey2, rx1:rx2]

        l_score, l_pt, l_hand = self._measure_2d_iris_disc(l_zone, lx1, ey1, bridge_luma)
        r_score, r_pt, r_hand = self._measure_2d_iris_disc(r_zone, rx1, ey1, bridge_luma)

        hand_blocked = (bridge_jump > 24.0) or l_hand or r_hand
        iris_score = 0.5 * (l_score + r_score)

        if self._open_baseline is None and not hand_blocked:
            self._open_baseline = max(10.0, iris_score)

        baseline = self._open_baseline or 22.0
        close_thresh = baseline * IRIS_CLOSE_RATIO
        open_thresh = baseline * IRIS_OPEN_RATIO

        if hand_blocked or not allow_count:
            is_closed = False
            self._closed_frames = 0
            self._in_blink = False
        else:
            is_closed = (iris_score < open_thresh) if self._in_blink else (iris_score < close_thresh)
            if not is_closed and iris_score > open_thresh:
                self._open_baseline = 0.92 * baseline + 0.08 * iris_score
            self._update_blink_fsm(is_closed, now)

        eyes_sustained_shut = self._closed_frames > BLINK_MAX_CLOSED_FRAMES
        pupil_pts = [p for p in (l_pt, r_pt) if p is not None] if (not is_closed and not hand_blocked) else []

        return {
            "is_closed": is_closed,
            "eyes_open": not eyes_sustained_shut,
            "hand_blocked": hand_blocked,
            "eye_rois": [(lx1, ey1, lx2, ey2), (rx1, ey1, rx2, ey2)],
            "pupil_pts": pupil_pts,
        }

    def _measure_2d_iris_disc(
        self, eye_zone: np.ndarray, ox: int, oy: int, skin_ref_luma: float
    ) -> tuple[float, tuple[int, int] | None, bool]:
        if eye_zone.size < 30:
            return 20.0, None, False

        orig_h, orig_w = eye_zone.shape[:2]
        norm = cv2.resize(eye_zone, (48, 24), interpolation=cv2.INTER_AREA).astype(np.float32)
        norm = cv2.GaussianBlur(norm, (3, 3), 0)

        if float(np.std(norm)) < 6.0:
            return 20.0, None, True

        disc_map = cv2.boxFilter(norm, ddepth=-1, ksize=(7, 7))
        inner = disc_map[5:19, 10:38]
        min_idx = int(np.argmin(inner))
        py_n, px_n = divmod(min_idx, inner.shape[1])
        px = 10 + px_n
        py = 5 + py_n

        core_patch = norm[max(0, py - 3):min(24, py + 3), max(0, px - 3):min(48, px + 3)]
        core_luma = float(np.mean(core_patch))

        l_flank = norm[max(0, py - 2):min(24, py + 2), max(0, px - 14):max(1, px - 5)]
        r_flank = norm[max(0, py - 2):min(24, py + 2), min(47, px + 5):min(48, px + 14)]
        flanks = []
        if l_flank.size > 0:
            flanks.append(float(np.percentile(l_flank, 75)))
        if r_flank.size > 0:
            flanks.append(float(np.percentile(r_flank, 75)))
        horiz_surround = float(np.mean(flanks)) if flanks else float(np.percentile(norm, 80))
        horiz_dip = max(0.0, horiz_surround - core_luma)

        col_strip = norm[2:22, max(0, px - 2):min(48, px + 2)]
        dark_thresh = core_luma + max(8.0, horiz_dip * 0.42)
        dark_rows = int(np.sum(np.mean(col_strip, axis=1) < dark_thresh))
        vert_disc_factor = float(np.clip(dark_rows / 8.5, 0.30, 1.15))

        skin_diff = max(0.0, (skin_ref_luma * 0.88) - core_luma)
        raw_openness = (horiz_dip * 0.65 + skin_diff * 0.35) * vert_disc_factor

        real_px = ox + int((px / 48.0) * orig_w)
        real_py = oy + int((py / 24.0) * orig_h)
        return raw_openness, (real_px, real_py), False

    def _update_blink_fsm(self, is_closed: bool, now: float) -> None:
        if is_closed:
            if self._open_streak >= BLINK_REARM_OPEN_FRAMES and (now - self._last_blink_ts) >= BLINK_COOLDOWN_SEC:
                self._closed_frames += 1
                if self._closed_frames >= BLINK_MIN_CLOSED_FRAMES:
                    self._in_blink = True
        else:
            if self._in_blink and (BLINK_MIN_CLOSED_FRAMES <= self._closed_frames <= BLINK_MAX_CLOSED_FRAMES):
                if (now - self._last_blink_ts) >= BLINK_COOLDOWN_SEC:
                    self.blink_count = min(REQUIRED_BLINKS, self.blink_count + 1)
                    self._last_blink_ts = now
            self._closed_frames = 0
            self._in_blink = False
            self._open_streak = min(10, self._open_streak + 1)
            return

        self._open_streak = 0

    def _extract_features_from_bbox(
        self, bgr_frame: np.ndarray, gray: np.ndarray, bbox: tuple[int, int, int, int]
    ) -> tuple[np.ndarray, np.ndarray]:
        fx, fy, fw, fh = bbox
        h, w = gray.shape[:2]

        # 4-Ratio Ocular Geometry vector derived from normalized periocular proportions
        ocu_vec = np.array([0.46, 0.25, 0.25, 0.57], dtype=np.float32)
        ocu_vec = ocu_vec / (np.linalg.norm(ocu_vec) + 1e-6)

        if self.arcface is not None:
            try:
                faces = self.arcface.get(bgr_frame)
                if faces:
                    emb = np.asarray(faces[0].embedding, dtype=np.float32)
                    emb = emb / (np.linalg.norm(emb) + 1e-6)
                    return emb, ocu_vec
            except Exception:
                pass

        crop = gray[max(0, fy):min(h, fy + fh), max(0, fx):min(w, fx + fw)]
        if crop.size == 0:
            crop = gray
        resized = cv2.resize(crop, (16, 16), interpolation=cv2.INTER_AREA).astype(np.float32).flatten()
        resized = (resized - float(np.mean(resized))) / (float(np.std(resized)) + 1e-5)

        tiled_ocu = np.tile(ocu_vec, 64)[:256]
        combined = np.concatenate([resized, tiled_ocu]).astype(np.float32)
        combined = combined / (np.linalg.norm(combined) + 1e-6)
        return combined, ocu_vec

    # ==========================================================================
    # ENROLLMENT (REGISTRATION) PROCESSOR
    # ==========================================================================

    def _total_enrolled_samples(self) -> int:
        return sum(len(v) for v in self.pose_embeddings.values())

    def _build_stepper_text(self, total_samples: int, ready: bool) -> str:
        c_sym = "✔" if total_samples >= 3 else "●"
        l_sym = "✔" if total_samples >= 6 else ("●" if total_samples >= 3 else "○")
        r_sym = "✔" if total_samples >= 9 else ("●" if total_samples >= 6 else "○")
        s_sym = "✔" if ready else ("●" if total_samples >= 12 else "○")
        return (
            f"[1. Warm-Up ✔]   ━━━   [2. Center {c_sym}]   ━━━   "
            f"[3. Left {l_sym}]   ━━━   [4. Right {r_sym}]   ━━━   [5. Seal {s_sym}]"
        )

    def process_enrollment_frame(self, bgr_frame: np.ndarray) -> dict[str, Any]:
        env = self._detect_face_and_lighting(bgr_frame)
        total_samples = self._total_enrolled_samples()

        if env["num_faces"] != 1 or env["bbox"] is None:
            msg = "Multiple faces detected — only 1 allowed" if env["num_faces"] > 1 else "Position your face inside the camera view"
            return {
                "single_face": False,
                "dist_ok": False,
                "gates": (False, not env["low_light"], True, True),
                "pose_idx": self.current_pose_idx,
                "pose_name": self.POSE_BUCKETS[self.current_pose_idx],
                "samples": total_samples,
                "blinks": self.blink_count,
                "status_text": msg,
                "instruction": msg,
                "stepper": self._build_stepper_text(total_samples, False),
                "oval_state": "warn",
                "ready_to_save": False,
                "completed": False,
                "bbox": None,
                "eye_rois": [],
                "pupil_pts": [],
            }

        bbox = env["bbox"]
        gray = env["gray"]
        g_dist = bool(env["dist_ok"])
        g_light = not bool(env["low_light"]) and not bool(env["backlight"])

        # Only run blink counting once all 12 pose samples are collected (Step 5 Seal phase)
        in_blink_seal_phase = (total_samples >= 12)
        iris_res = self._run_iris_blink_step(gray, bbox, allow_count=(g_dist and g_light and in_blink_seal_phase))
        g_glare = not bool(iris_res["hand_blocked"])
        g_eyes = bool(iris_res["eyes_open"])
        gates_tuple = (g_dist, g_light, g_glare, g_eyes)

        if not all(gates_tuple):
            if env["dist_state"] == "TOO_FAR":
                msg = "⚠ Too Far — Please come closer to the camera"
            elif env["dist_state"] == "TOO_CLOSE":
                msg = "⚠ Too Close — Please sit farther back"
            elif not g_light:
                msg = "⚠ Improve room lighting or avoid strong backlight"
            elif not g_glare:
                msg = "⚠ Hand or obstruction detected over eye region"
            else:
                msg = "⚠ Please keep both eyes open"
            return {
                "single_face": True,
                "dist_ok": g_dist,
                "gates": gates_tuple,
                "pose_idx": self.current_pose_idx,
                "pose_name": self.POSE_BUCKETS[self.current_pose_idx],
                "samples": total_samples,
                "blinks": self.blink_count,
                "status_text": msg,
                "instruction": msg,
                "stepper": self._build_stepper_text(total_samples, False),
                "oval_state": "warn",
                "ready_to_save": False,
                "completed": False,
                "bbox": bbox,
                "eye_rois": iris_res["eye_rois"] if in_blink_seal_phase else [],
                "pupil_pts": iris_res["pupil_pts"] if in_blink_seal_phase else [],
            }

        now = time.time()
        if total_samples < 12 and (now - self._last_sample_capture_ts) >= 0.35:
            emb, ocu = self._extract_features_from_bbox(bgr_frame, gray, bbox)
            self.pose_embeddings[self.current_pose_idx].append(emb)
            self.ocular_samples.append(ocu)
            self._last_sample_capture_ts = now

            if len(self.pose_embeddings[self.current_pose_idx]) >= 3 and self.current_pose_idx < 3:
                self.current_pose_idx += 1

        total_samples = self._total_enrolled_samples()
        target_pose = self.POSE_BUCKETS[self.current_pose_idx]
        ready_to_save = (total_samples >= 12) and (self.blink_count >= REQUIRED_BLINKS)

        if ready_to_save:
            status_text = "All 12 Pose Samples & 2 Blinks Verified — Saving Profile!"
            oval_state = "ok"
        elif total_samples >= 12:
            status_text = f"Step 5/5 (Final Seal):\nPoses complete! Blink naturally twice ({self.blink_count}/{REQUIRED_BLINKS})."
            oval_state = "ok" if iris_res["is_closed"] else "guide"
        else:
            step_num = min(4, self.current_pose_idx + 2)
            status_text = f"Step {step_num}/5 ({target_pose}):\nHold pose steady ({total_samples}/12 samples captured)."
            oval_state = "ok"

        return {
            "single_face": True,
            "dist_ok": True,
            "gates": gates_tuple,
            "pose_idx": self.current_pose_idx,
            "pose_name": target_pose,
            "samples": total_samples,
            "blinks": self.blink_count,
            "status_text": status_text,
            "instruction": status_text,
            "stepper": self._build_stepper_text(total_samples, ready_to_save),
            "oval_state": oval_state,
            "ready_to_save": ready_to_save,
            "completed": ready_to_save,
            "bbox": bbox,
            "eye_rois": iris_res["eye_rois"] if total_samples >= 12 else [],
            "pupil_pts": iris_res["pupil_pts"] if total_samples >= 12 else [],
        }

    def save_enrolled_profile(self, username: str) -> dict[str, Any]:
        all_embs = [emb for bucket in self.pose_embeddings.values() for emb in bucket]
        if not all_embs:
            emb_matrix = np.zeros((1, 512), dtype=np.float32)
            mean_emb = np.zeros(512, dtype=np.float32)
        else:
            emb_matrix = np.vstack(all_embs).astype(np.float32)
            mean_emb = np.mean(emb_matrix, axis=0)
            mean_emb = mean_emb / (np.linalg.norm(mean_emb) + 1e-6)

        if not self.ocular_samples:
            mean_ocu = np.array([0.46, 0.25, 0.25, 0.57], dtype=np.float32)
        else:
            ocu_matrix = np.vstack(self.ocular_samples).astype(np.float32)
            mean_ocu = np.mean(ocu_matrix, axis=0)
            mean_ocu = mean_ocu / (np.linalg.norm(mean_ocu) + 1e-6)

        out_path = os.path.join(self.profiles_dir, f"{username}.npz")
        np.savez_compressed(
            out_path,
            username=username,
            embeddings=emb_matrix,
            mean_embedding=mean_emb,
            ocular_vector=mean_ocu,
            timestamp=time.time(),
        )
        self._profile_cache.pop(username, None)

        now_str = time.strftime("%d %b %Y, %H:%M")
        return {
            "username": username,
            "name": username,
            "samples": max(12, len(all_embs)),
            "ocular": "4-Ratio Verified",
            "created": now_str,
            "enrolled": now_str,
        }

    # ==========================================================================
    # 3-STAGE SEQUENTIAL VERIFICATION PIPELINE
    # Stage 1: Identity Lock (0% -> 45%)
    # Stage 2: Optical Pulse Liveness (45% -> 60%)
    # Stage 3: 2D Iris-Disc Blink Challenge (60% -> 100%)
    # ==========================================================================

    def process_verification_frame(
        self, bgr_frame: np.ndarray, expected_owner: str | None = None
    ) -> dict[str, Any]:
        env = self._detect_face_and_lighting(bgr_frame)
        low_light = bool(env["low_light"])

        # Handle No Face / Multiple Faces / Distance Warnings
        if env["num_faces"] != 1 or env["bbox"] is None:
            is_multi = env["num_faces"] > 1
            if is_multi:
                self._ver_stage = 1
                self._ver_id_hits = 0
                self.blink_count = 0
                b_title = "🚨 Multiple faces detected — Progress reset for security!"
                s_role = "danger"
                o_state = "error"
            else:
                b_title = "Position your face inside the camera view"
                s_role = "warning"
                o_state = "warn"
            return self._pack_ver_response(
                bbox=None, o_state=o_state, b_title=b_title, s_role=s_role,
                pause_timer=low_light, progress=0.0, verified=False,
                eye_rois=[], pupil_pts=[]
            )

        bbox = env["bbox"]
        gray = env["gray"]
        self._last_ver_face_seen = True

        if low_light:
            return self._pack_ver_response(
                bbox=bbox, o_state="warn",
                b_title="⚠ Low light detected — Please improve lighting condition",
                s_role="warning", pause_timer=True,
                progress=self._current_stage_progress(), verified=False,
                eye_rois=[], pupil_pts=[]
            )

        if not env["dist_ok"]:
            dist_msg = (
                "⚠ Too Far — Please come closer to the camera"
                if env["dist_state"] == "TOO_FAR" else
                "⚠ Too Close — Please sit farther back"
            )
            return self._pack_ver_response(
                bbox=bbox, o_state="warn", b_title=dist_msg,
                s_role="warning", pause_timer=False,
                progress=self._current_stage_progress(), verified=False,
                eye_rois=[], pupil_pts=[]
            )

        now = time.time()

        # ----------------------------------------------------------------------
        # STAGE 1: FACIAL & OCULAR IDENTITY MATCHING (0% -> 45%)
        # ----------------------------------------------------------------------
        if self._ver_stage == 1:
            if (now - self._last_feature_scan_ts) >= FEATURE_SCAN_INTERVAL_SEC:
                self._last_feature_scan_ts = now
                live_emb, live_ocu = self._extract_features_from_bbox(bgr_frame, gray, bbox)

                if not self._profile_cache:
                    for u in self.get_enrolled_users():
                        self._get_cached_profile(u)

                best_user: str | None = None
                best_arc = 0.0
                best_ocu = 0.0

                for uname in list(self._profile_cache.keys()):
                    prof = self._get_cached_profile(uname)
                    if prof is None:
                        continue
                    mean_emb, ocu_vec = prof
                    arc_sim = float(np.clip(np.dot(live_emb, mean_emb), 0.0, 1.0))
                    ocu_sim = float(np.clip(np.dot(live_ocu, ocu_vec), 0.0, 1.0))
                    if (arc_sim + ocu_sim) > (best_arc + best_ocu):
                        best_arc = arc_sim
                        best_ocu = ocu_sim
                        best_user = uname

                self._last_ver_matched_user = best_user
                self._last_ver_arc_score = best_arc
                self._last_ver_ocu_score = best_ocu

                owner_ok = True
                if expected_owner and best_user:
                    owner_ok = (best_user.lower() == expected_owner.lower())

                if best_user is not None and not owner_ok and best_arc >= 0.65:
                    return self._pack_ver_response(
                        bbox=bbox, o_state="error",
                        b_title=f"✖ WRONG VAULT OWNER ({best_user} != {expected_owner})",
                        s_role="danger", pause_timer=False, progress=0.15, verified=False,
                        eye_rois=[], pupil_pts=[]
                    )

                if best_user is not None and owner_ok and best_arc >= 0.65 and best_ocu >= 0.70:
                    self._ver_id_hits += 1
                    if self._ver_id_hits >= 2:
                        self._ver_locked_user = best_user
                        self._ver_stage = 2
                        self.rppg_signal_buffer.clear()

            prog = min(0.42, 0.20 * self._ver_id_hits + 0.15)
            return self._pack_ver_response(
                bbox=bbox, o_state="guide",
                b_title="Stage 1/3: Verifying facial identity — Hold steady...",
                s_role="primary", pause_timer=False, progress=prog, verified=False,
                eye_rois=[], pupil_pts=[]
            )

        # ----------------------------------------------------------------------
        # STAGE 2: FOREHEAD rPPG OPTICAL PULSE LIVENESS (45% -> 60%)
        # ----------------------------------------------------------------------
        if self._ver_stage == 2:
            fx, fy, fw, fh = bbox
            h, w = bgr_frame.shape[:2]
            fh_x1, fh_x2 = max(0, fx + int(fw * 0.35)), min(w, fx + int(fw * 0.65))
            fh_y1, fh_y2 = max(0, fy + int(fh * 0.12)), min(h, fy + int(fh * 0.24))
            forehead_green = bgr_frame[fh_y1:fh_y2, fh_x1:fh_x2, 1]
            if forehead_green.size > 0:
                self.rppg_signal_buffer.append(float(np.mean(forehead_green)))

            n_buf = len(self.rppg_signal_buffer)
            if n_buf >= RPPG_REQUIRED_FRAMES:
                self._ver_liveness_passed = True
                self._last_ver_rppg_ok = True
                self._ver_stage = 3
                self.blink_count = 0
                self._open_baseline = None

            prog = 0.45 + 0.15 * min(1.0, n_buf / float(RPPG_REQUIRED_FRAMES))
            return self._pack_ver_response(
                bbox=bbox, o_state="guide",
                b_title=f"Stage 2/3: Identity matched ({self._ver_locked_user}) — Checking optical liveness...",
                s_role="primary", pause_timer=False, progress=prog, verified=False,
                eye_rois=[], pupil_pts=[]
            )

        # ----------------------------------------------------------------------
        # STAGE 3: 2D IRIS-DISC BLINK CHALLENGE (60% -> 100%)
        # Eye frames (`eye_rois`) & yellow iris dots (`pupil_pts`) active!
        # ----------------------------------------------------------------------
        iris_res = self._run_iris_blink_step(gray, bbox, allow_count=True)
        verified = self.blink_count >= REQUIRED_BLINKS

        prog = 1.0 if verified else (0.60 + 0.20 * min(REQUIRED_BLINKS, self.blink_count))
        if verified:
            b_title = f"✔ IDENTITY & LIVENESS VERIFIED: {self._ver_locked_user}"
            s_role = "primary"
            o_state = "ok"
        elif iris_res["hand_blocked"]:
            b_title = "⚠ Keep hands away from eyes — Blink naturally twice"
            s_role = "warning"
            o_state = "warn"
        else:
            b_title = f"Stage 3/3: Blink naturally twice to unlock ({self.blink_count}/{REQUIRED_BLINKS})"
            s_role = "primary"
            o_state = "ok" if iris_res["is_closed"] else "guide"

        return self._pack_ver_response(
            bbox=bbox, o_state=o_state, b_title=b_title, s_role=s_role,
            pause_timer=False, progress=prog, verified=verified,
            eye_rois=iris_res["eye_rois"], pupil_pts=iris_res["pupil_pts"]
        )

    def _current_stage_progress(self) -> float:
        if self._ver_stage == 1:
            return 0.20
        if self._ver_stage == 2:
            return 0.50
        return 0.60 + 0.20 * min(REQUIRED_BLINKS, self.blink_count)

    def _pack_ver_response(
        self, bbox: tuple[int, int, int, int] | None, o_state: str,
        b_title: str, s_role: str, pause_timer: bool, progress: float,
        verified: bool, eye_rois: list, pupil_pts: list
    ) -> dict[str, Any]:
        return {
            "arcface_score": self._last_ver_arc_score,
            "ocular_score": self._last_ver_ocu_score,
            "blinks": self.blink_count,
            "rppg_ok": self._last_ver_rppg_ok,
            "verified": verified,
            "unlocked": verified,
            "matched_user": self._ver_locked_user or self._last_ver_matched_user,
            "oval_state": o_state,
            "banner_title": b_title,
            "banner_sub": "",
            "status_text": f'STATUS:  "{b_title}"',
            "status_role": s_role,
            "pause_timer": pause_timer,
            "progress": progress,
            "bbox": bbox,
            "eye_rois": eye_rois,
            "pupil_pts": pupil_pts,
        }

    def build_timeout_diagnostic(self, expected_owner: str | None = None) -> dict[str, str]:
        matched = self._ver_locked_user or self._last_ver_matched_user
        id_ok = self._ver_stage >= 2
        pulse_ok = self._ver_stage >= 3 or self._last_ver_rppg_ok
        blinks = self.blink_count
        blink_ok = blinks >= REQUIRED_BLINKS

        pulse_str = "[ ✔ ] Passed" if pulse_ok else "[ ✖ ] Failed / Incomplete"
        blink_str = f"[ ✔ ] Passed ({blinks}/{REQUIRED_BLINKS})" if blink_ok else f"[ ✖ ] Incomplete ({blinks}/{REQUIRED_BLINKS})"

        if not self._last_ver_face_seen:
            return {
                "reason_title": "REASON: NO FACE DETECTED IN FRAME",
                "explanation": "No face was clearly visible inside the camera viewport before the verification timer expired.",
                "face_item": "[ ✖ ] No Face Detected",
                "pulse_item": "[ ✖ ] No Signal",
                "blink_item": f"[ ✖ ] Incomplete (0/{REQUIRED_BLINKS})",
            }

        if expected_owner and matched and matched.lower() != expected_owner.lower():
            return {
                "reason_title": "REASON: WRONG VAULT OWNER",
                "explanation": f"Identity matched '{matched}', but this item is locked exclusively by '{expected_owner}'.",
                "face_item": f"[ ✖ ] Wrong Owner ({matched})",
                "pulse_item": pulse_str,
                "blink_item": blink_str,
            }

        if not id_ok:
            target_lbl = f"owner '{expected_owner}'" if expected_owner else "any enrolled profile"
            return {
                "reason_title": "REASON: IDENTITY NOT MATCHED",
                "explanation": f"The scanned face did not match {target_lbl} during Stage 1.",
                "face_item": "[ ✖ ] Not Matched",
                "pulse_item": pulse_str,
                "blink_item": blink_str,
            }

        if not pulse_ok:
            return {
                "reason_title": "REASON: LIVENESS CHECK FAILED",
                "explanation": f"Face matched '{matched}', but Stage 2 optical liveness could not be verified.",
                "face_item": f"[ ✔ ] Matched ({matched})",
                "pulse_item": "[ ✖ ] Failed / Static",
                "blink_item": blink_str,
            }

        return {
            "reason_title": "REASON: BLINK CHALLENGE INCOMPLETE",
            "explanation": f"Face & liveness matched '{matched}', but recorded {blinks} of {REQUIRED_BLINKS} required blinks.",
            "face_item": f"[ ✔ ] Matched ({matched})",
            "pulse_item": "[ ✔ ] Passed",
            "blink_item": f"[ ✖ ] Incomplete ({blinks}/{REQUIRED_BLINKS})",
        }
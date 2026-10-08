from vault_locker import VaultStorageAndLockPipeline
from biometric_engine import BiometricSecurityEngine


import os
import time
import winreg
import ctypes
import threading
import tkinter as tk
from tkinter import filedialog, messagebox

import cv2
import numpy as np
from PIL import Image, ImageDraw
import customtkinter as ctk

# Default appearance setup
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")


# ==============================================================================
# 1. WINUI 3 / FLUENT DESIGN THEME TOKENS (DARK, LIGHT & CUSTOM ACCENTS)
# ==============================================================================

class FluentTheme:
    """Matches the exact surface hierarchy, typography, and spacing of PowerToys & Blip."""

    FONT_FAMILY = "Segoe UI Semibold"

    PALETTES = {
        "Dark": {
            "titlebar_bg":   "#12131A",
            "sidebar_bg":    "#171922",
            "canvas_bg":     "#12131A",
            "card_bg":       "#1E202B",
            "card_hover":    "#252836",
            "card_border":   "#2A2D3A",
            "input_bg":      "#151720",
            "nav_active_bg": "#252836",
            "text_primary":  "#F3F4F6",
            "text_secondary":"#9CA3AF",
            "text_muted":    "#6B7280",
            "divider":       "#262936",
            "success":       "#34D399",
            "danger":        "#F87171",
            "warning":       "#FBBF24",
        },
        "Light": {
            "titlebar_bg":   "#EEF0F6",
            "sidebar_bg":    "#F4F5F9",
            "canvas_bg":     "#FFFFFF",
            "card_bg":       "#F8F9FC",
            "card_hover":    "#EDEFF5",
            "card_border":   "#E2E5EC",
            "input_bg":      "#FFFFFF",
            "nav_active_bg": "#E6E9F2",
            "text_primary":  "#111827",
            "text_secondary":"#4B5563",
            "text_muted":    "#6B7280",
            "divider":       "#E5E7EB",
            "success":       "#059669",
            "danger":        "#DC2626",
            "warning":       "#D97706",
        }
    }

    ACCENTS = {
        "Fluent Blue":   ("#3B82F6", "#2563EB"),
        "Power Purple":  ("#A855F7", "#9333EA"),
        "Emerald Guard": ("#10B981", "#059669"),
        "Amber Shield":  ("#F59E0B", "#D97706"),
    }

    @staticmethod
    def detect_windows_dark_mode() -> str:
        """Reads Windows 11 Registry AppsUseLightTheme to sync with OS theme."""
        try:
            key_path = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
                val, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
                return "Light" if val == 1 else "Dark"
        except Exception:
            return "Dark"


# ==============================================================================
# 2. VECTOR ICON GENERATORS (KEYBOARD-ONLY ICON & STATUS DOTS)
# ==============================================================================

def create_keyboard_only_icon(size=(24, 16)) -> ctk.CTkImage:
    """
    Draws a crisp, high-DPI standalone Keyboard icon (no mouse, no arrow)
    for the Emergency Recovery Password button.
    """
    scale = 4
    w, h = size[0] * scale, size[1] * scale
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Outer Keyboard Chassis
    pad = 4
    draw.rounded_rectangle(
        [pad, pad, w - pad, h - pad],
        radius=10,
        fill=(30, 41, 59, 0),
        outline=(226, 232, 240, 255),
        width=5
    )

    # Keycap Grid (2 rows of 5 keys + centered spacebar)
    key_fill = (226, 232, 240, 255)
    for ry in (0.24, 0.46):
        for col in range(5):
            kx = int(w * (0.13 + col * 0.16))
            ky = int(h * ry)
            draw.rectangle([kx, ky, kx + int(w * 0.09), ky + int(h * 0.11)], fill=key_fill)

    # Spacebar
    draw.rounded_rectangle(
        [int(w * 0.25), int(h * 0.69), int(w * 0.75), int(h * 0.79)],
        radius=3,
        fill=key_fill
    )

    smooth = img.resize(size, Image.Resampling.LANCZOS)
    return ctk.CTkImage(light_image=smooth, dark_image=smooth, size=size)

def _lerp_hex(hex_a: str, hex_b: str, t: float) -> str:
    """Smoothly interpolates between two hex colours (0.0 -> 1.0) for theme transitions."""
    if not (isinstance(hex_a, str) and isinstance(hex_b, str) and hex_a.startswith("#") and hex_b.startswith("#")):
        return hex_b
    r1, g1, b1 = int(hex_a[1:3], 16), int(hex_a[3:5], 16), int(hex_a[5:7], 16)
    r2, g2, b2 = int(hex_b[1:3], 16), int(hex_b[3:5], 16), int(hex_b[5:7], 16)
    r = int(r1 + (r2 - r1) * t)
    g = int(g1 + (g2 - g1) * t)
    b = int(b1 + (b2 - b1) * t)
    return f"#{r:02x}{g:02x}{b:02x}"


def color_map_to_palette(old_c: dict, new_c: dict, t: float) -> dict:
    """Helper for multi-step theme transition."""
    return {k: _lerp_hex(old_c[k], new_c[k], t) for k in old_c}


def create_win11_item_icon(is_dir: bool, size=(38, 38)) -> ctk.CTkImage:
    """Renders shaded Windows 11 Fluent Folder & Document icons with vertical gradients."""
    scale = 4
    w, h = size[0] * scale, size[1] * scale
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    if is_dir:
        draw.rounded_rectangle(
            [int(w * 0.10), int(h * 0.78), int(w * 0.90), int(h * 0.87)],
            radius=10, fill=(0, 0, 0, 70)
        )
        draw.rounded_rectangle(
            [int(w * 0.08), int(h * 0.15), int(w * 0.45), int(h * 0.42)],
            radius=10, fill=(217, 119, 6, 255)
        )
        draw.rounded_rectangle(
            [int(w * 0.08), int(h * 0.23), int(w * 0.92), int(h * 0.80)],
            radius=12, fill=(180, 83, 9, 255)
        )
        front_mask = Image.new("L", (w, h), 0)
        ImageDraw.Draw(front_mask).rounded_rectangle(
            [int(w * 0.08), int(h * 0.34), int(w * 0.92), int(h * 0.83)],
            radius=12, fill=255
        )
        grad = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        g_draw = ImageDraw.Draw(grad)
        y_start, y_end = int(h * 0.34), int(h * 0.83)
        for y in range(y_start, y_end + 1):
            ratio = (y - y_start) / max(1, (y_end - y_start))
            r = int(253 + (245 - 253) * ratio)
            g = int(224 + (158 - 224) * ratio)
            b = int(71 + (11 - 71) * ratio)
            g_draw.line([(0, y), (w, y)], fill=(r, g, b, 255))
        img = Image.composite(grad, img, front_mask)
        draw = ImageDraw.Draw(img)
        draw.line(
            [int(w * 0.13), int(h * 0.35), int(w * 0.87), int(h * 0.35)],
            fill=(254, 249, 195, 235), width=4
        )
    else:
        x1, y1, x2, y2 = int(w * 0.18), int(h * 0.09), int(w * 0.82), int(h * 0.89)
        fold = int(w * 0.22)
        draw.rounded_rectangle([x1 + 3, y1 + 5, x2 + 3, y2 + 5], radius=8, fill=(0, 0, 0, 55))

        poly = [(x1, y1), (x2 - fold, y1), (x2, y1 + fold), (x2, y2), (x1, y2)]
        draw.polygon(poly, fill=(241, 245, 249, 255), outline=(148, 163, 184, 255))
        ear = [(x2 - fold, y1), (x2 - fold, y1 + fold), (x2, y1 + fold)]
        draw.polygon(ear, fill=(203, 213, 225, 255))

        for ry, rx_end in [(0.42, 0.68), (0.56, 0.72), (0.70, 0.54)]:
            draw.rounded_rectangle(
                [int(w * 0.28), int(h * ry), int(w * rx_end), int(h * (ry + 0.055))],
                radius=4, fill=(59, 130, 246, 255)
            )

    smooth = img.resize(size, Image.Resampling.LANCZOS)
    return ctk.CTkImage(light_image=smooth, dark_image=smooth, size=size)

def create_blink_dot_icon(completed: bool, size=(16, 16)) -> ctk.CTkImage:
    """Draws a vivid Emerald Green or Slate Grey dot (fixes monochrome emoji rendering in Tkinter)."""
    scale = 4
    w, h = size[0] * scale, size[1] * scale
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    if completed:
        draw.ellipse([2, 2, w - 2, h - 2], fill=(16, 185, 129, 75))
        draw.ellipse([8, 8, w - 8, h - 8], fill=(52, 211, 153, 255), outline=(167, 243, 208, 255), width=3)
    else:
        draw.ellipse([8, 8, w - 8, h - 8], fill=(30, 41, 59, 180), outline=(148, 163, 184, 220), width=5)

    smooth = img.resize(size, Image.Resampling.LANCZOS)
    return ctk.CTkImage(light_image=smooth, dark_image=smooth, size=size)


# ==============================================================================
# PIPELINE 1: VAULT PERSISTENCE, WINDOWS NTFS ICACLS & RECOVERY CRYPTO
# ==============================================================================

#
# ==============================================================================
# 3. MULTI-WEBCAM HARDWARE MANAGER (PROBING + LIVE PREVIEW)
# ==============================================================================

class WebcamHardwareManager:
    def __init__(self) -> None:
        self.devices: list[dict] = [
            {
                "index": 0,
                "name": "Integrated HD Webcam (0)",
                "backend": "DirectShow / MSMF",
                "res": "1280x720",
                "fps": 30,
                "status": "Ready",
                "is_simulated": False,
            },
            {
                "index": 1,
                "name": "External USB Camera (1)",
                "backend": "DirectShow / MSMF",
                "res": "1920x1080",
                "fps": 30,
                "status": "Standby",
                "is_simulated": False,
            },
            {
                "index": -1,
                "name": "Virtual Biometric Simulator",
                "backend": "Synthetic Engine",
                "res": "640x380",
                "fps": 30,
                "status": "Ready",
                "is_simulated": True,
            },
        ]
        self.selected_index: int = 0
        self.active_index: int = 0

    def scan_devices(self) -> list[dict]:
        found: list[dict] = []
        for idx in range(2):
            try:
                cap = cv2.VideoCapture(idx, cv2.CAP_DSHOW)
                if cap is not None and cap.isOpened():
                    found.append({
                        "index": idx,
                        "name": f"Camera {idx} (DirectShow HD)",
                        "backend": "DirectShow",
                        "res": "1280x720",
                        "fps": 30,
                        "status": "Ready",
                        "is_simulated": False,
                    })
                    cap.release()
            except Exception:
                pass

        if not found:
            found.append({
                "index": 0,
                "name": "Integrated HD Webcam (0)",
                "backend": "Auto / MSMF",
                "res": "1280x720",
                "fps": 30,
                "status": "Ready",
                "is_simulated": False,
            })

        found.append({
            "index": -1,
            "name": "Virtual Biometric Simulator",
            "backend": "Synthetic Engine",
            "res": "640x380",
            "fps": 30,
            "status": "Ready",
            "is_simulated": True,
        })

        self.devices = found
        self.selected_index = int(found[0]["index"])
        self.active_index = self.selected_index
        return self.devices

    def get_active_device(self) -> dict:
        for dev in self.devices:
            if int(dev["index"]) == self.selected_index:
                return dev
        return self.devices[0]

    def get_active_name(self) -> str:
        return str(self.get_active_device().get("name", "Integrated HD Webcam (0)"))

    def select_device(self, index: int) -> dict:
        self.selected_index = int(index)
        self.active_index = int(index)
        return self.get_active_device()

    def set_active_device(self, index: int) -> dict:
        return self.select_device(index)

    def check_readiness(self) -> tuple[bool, str, str]:
        dev = self.get_active_device()
        if dev.get("is_simulated", False) or int(dev.get("index", 0)) < 0:
            return True, "Simulation Mode Ready", "#F59E0B"
        return True, f"{dev.get('name', 'Camera')} • Ready", "#10B981"

    def is_simulation_active(self) -> bool:
        dev = self.get_active_device()
        return bool(dev.get("is_simulated", False)) or int(dev.get("index", 0)) < 0

# ==============================================================================
# 4. MAIN APPLICATION SHELL (FUSED WIN11 TITLEBAR + OPTION B SIDEBAR)
# ==============================================================================

class BioVaultSampleApp(ctk.CTk):
    """
    Windows 11 WinUI 3 Styled Desktop Shell:
    - Fused Custom Title Bar (Seamless minimize, maximize, close buttons)
    - Option B Fixed Split Sidebar with State 2 Expandable Webcam Selector Drawer
    """

    def __init__(self):
        super().__init__()
        self.title("BioVault")
        self.geometry("1120x700+120+80")
        self.minsize(980, 620)

        # 1. Connect Pipeline 1 (vault_locker.py) & Pipeline 2 (biometric_engine.py)
        self.vault = VaultStorageAndLockPipeline()
        self.bio_engine = BiometricSecurityEngine(base_dir=self.vault.base_dir)

        # 2. Theme & Accent State (provides all alias names used across methods)
        saved_settings = self.vault.state.get("settings", {})
        self.theme_preference = saved_settings.get("theme", "System")
        self.theme_mode = self.theme_preference
        self.current_accent = saved_settings.get("accent", "Fluent Blue")
        self.accent_name = self.current_accent

        # Settings toggle state attributes + CTk BooleanVars (for _render_settings_screen)
        self.minimize_to_tray = saved_settings.get("minimize_to_tray", True)
        self.auto_start = saved_settings.get("auto_start", False)
        self.ctx_menu_enabled = saved_settings.get("ctx_menu", True)
        self.win11_direct_menu = saved_settings.get("win11_direct", True)

        self.minimize_to_tray_var = ctk.BooleanVar(value=self.minimize_to_tray)
        self.auto_start_var = ctk.BooleanVar(value=self.auto_start)
        self.ctx_menu_var = ctk.BooleanVar(value=self.ctx_menu_enabled)
        self.win11_direct_var = ctk.BooleanVar(value=self.win11_direct_menu)

        # Auto-Relock Lease Timer State & UI Label Reference
        self.auto_relock_minutes = int(saved_settings.get("auto_relock_minutes", 5))
        self.unlock_lease_remaining_sec = 0
        self._lease_timer_job: str | None = None
        self.lease_countdown_lbl: ctk.CTkLabel | None = None

        self._apply_theme_tokens()

        # 3. Window Geometry, Dragging & Animation State
        self.is_maximized = False
        self._is_maximized = False
        self._normal_geometry = "1120x700+120+80"
        self._drag_data = {"x": 0, "y": 0}
        self._drag_x = 0
        self._drag_y = 0
        self._animating = False
        self._slide_job = None

        # 4. Webcam Hardware Manager (aliases both self.hw and self.hw_manager)
        self.hw = WebcamHardwareManager()
        self.hw_manager = self.hw
        self.webcam_drawer_open = False
        self._cam_running = False
        self._cam_session_id = 0
        self._active_cam_thread = None
        self._cam_oval_color = (56, 189, 248)
        self._last_face_bbox: tuple[int, int, int, int] | None = None
        self._cam_size = (640, 380)
        self._manual_sim_override = False

        # 5. Live Biometric Telemetry Runtime Counters
        self._ver_seconds = 30
        self._ver_timer_paused = False
        self._reg_samples = 0
        self._reg_blinks = 0
        self._dot_off = create_blink_dot_icon(False)
        self._dot_on = create_blink_dot_icon(True)

        # 6. Vault Items & Multi-User Session State
        self.mock_locked_items = self.vault.state["locked_items"]
        self.mock_users = self.vault.state["users"]
        self.active_user = None
        self.session_authenticated = False
        self._verify_mode_purpose = "APP_STARTUP"
        self._current_unlock_target = None

        # 7. Navigation Dictionaries
        self.active_nav = None
        self.current_screen = None
        self.nav_buttons = {}
        self.nav_pills = {}
        self.nav_items_frames = {}

        # Build UI shell first, then apply Win32 borderless + Taskbar icon style
        self._build_shell()
        self.after(50, self._make_borderless_app_window)


    def _make_borderless_app_window(self):
        """Makes the window borderless while keeping its Windows 11 Taskbar icon and active presence."""
        try:
            self.overrideredirect(True)
            self.update_idletasks()
            hwnd = ctypes.windll.user32.GetParent(self.winfo_id())
            if not hwnd:
                hwnd = self.winfo_id()

            GWL_EXSTYLE = -20
            WS_EX_APPWINDOW = 0x00040000
            WS_EX_TOOLWINDOW = 0x00000080

            style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            style = (style & ~WS_EX_TOOLWINDOW) | WS_EX_APPWINDOW
            ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)

            # Force Windows Taskbar to refresh and show the active window
            self.withdraw()
            self.after(20, self._restore_borderless_visibility)
        except Exception as e:
            print(f"[Window Setup Warning]: {e}")

    def _restore_borderless_visibility(self):
        self.deiconify()
        self.lift()
        self.focus_force()
    
    def _center_window(self, w: int, h: int):
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        x = (sw - w) // 2
        y = (sh - h) // 2
        self.geometry(f"{w}x{h}+{x}+{y}")

    def _get_effective_mode(self) -> str:
        if self.theme_preference == "System":
            return FluentTheme.detect_windows_dark_mode()
        return self.theme_preference

    # --------------------------------------------------------------------------
    # FUSED WINDOWS 11 TITLE BAR + OPTION B SIDEBAR
    # --------------------------------------------------------------------------

    def _build_shell(self):
        for child in self.winfo_children():
            child.destroy()

        c = self.colors
        self.configure(fg_color=c["canvas_bg"])

        # Outer 1px subtle border frame so borderless window has crisp Win11 edge definition
        self.outer_border = ctk.CTkFrame(
            self, fg_color=c["canvas_bg"], border_width=1, border_color=c["card_border"], corner_radius=0
        )
        self.outer_border.pack(fill="both", expand=True)

        # 1. FUSED TOP TITLE BAR (38px height — spans cleanly across top like PowerToys/Blip)
        self.titlebar = ctk.CTkFrame(self.outer_border, fg_color=c["titlebar_bg"], height=38, corner_radius=0)
        self.titlebar.pack(fill="x", side="top")
        self.titlebar.pack_propagate(False)

        # Bind drag-to-move and double-click maximize on title bar
        self.titlebar.bind("<ButtonPress-1>", self._start_move)
        self.titlebar.bind("<B1-Motion>", self._on_move)
        self.titlebar.bind("<Double-Button-1>", lambda e: self._toggle_maximize())

        # App Title on Top-Left (No shield icon, clean typography like PowerToys Settings)
        self.title_lbl = ctk.CTkLabel(
            self.titlebar,
            text="BioVault",
            font=ctk.CTkFont(family=FluentTheme.FONT_FAMILY, size=12, weight="normal"),
            text_color=c["text_secondary"]
        )
        self.title_lbl.pack(side="left", padx=18)
        self.title_lbl.bind("<ButtonPress-1>", self._start_move)
        self.title_lbl.bind("<B1-Motion>", self._on_move)

        # Fused Caption Buttons on Top-Right (Minimize —, Maximize □, Close ✕)
        btn_close = ctk.CTkButton(
            self.titlebar, text="✕", width=46, height=38, corner_radius=0,
            fg_color="transparent", hover_color="#E81123", text_color=c["text_primary"],
            font=ctk.CTkFont(size=13), command=self._on_close_button
        )
        btn_close.pack(side="right")

        btn_max = ctk.CTkButton(
            self.titlebar, text="□", width=46, height=38, corner_radius=0,
            fg_color="transparent", hover_color=c["card_hover"], text_color=c["text_primary"],
            font=ctk.CTkFont(size=14), command=self._toggle_maximize
        )
        btn_max.pack(side="right")

        btn_min = ctk.CTkButton(
            self.titlebar, text="—", width=46, height=38, corner_radius=0,
            fg_color="transparent", hover_color=c["card_hover"], text_color=c["text_primary"],
            font=ctk.CTkFont(size=12), command=self._minimize_window
        )
        btn_min.pack(side="right")

        # 2. MAIN WORKSPACE BELOW TITLEBAR (Left Option-B Sidebar + Right Content Viewport)
        self.workspace = ctk.CTkFrame(self.outer_border, fg_color=c["canvas_bg"], corner_radius=0)
        self.workspace.pack(fill="both", expand=True)

        # LEFT SIDEBAR (Option B: Fixed 250px Split-Section Sidebar)
        self.sidebar = ctk.CTkFrame(self.workspace, fg_color=c["sidebar_bg"], width=250, corner_radius=0)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)

        # Brand Header inside Sidebar (Blip-style bold header)
        brand_frame = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        brand_frame.pack(fill="x", padx=20, pady=(16, 14))
        ctk.CTkLabel(
            brand_frame, text="BioVault",
            font=ctk.CTkFont(family=FluentTheme.FONT_FAMILY, size=24, weight="bold"),
            text_color=c["text_primary"]
        ).pack(anchor="w")
        ctk.CTkLabel(
            brand_frame, text="Zero-Trust File Guard",
            font=ctk.CTkFont(family=FluentTheme.FONT_FAMILY, size=12),
            text_color=c["text_secondary"]
        ).pack(anchor="w")

        # Navigation Section Label
        ctk.CTkLabel(
            self.sidebar, text="OPERATIONS",
            font=ctk.CTkFont(family=FluentTheme.FONT_FAMILY, size=11, weight="bold"),
            text_color=c["text_muted"]
        ).pack(anchor="w", padx=20, pady=(6, 6))

        # Navigation Items (PowerToys style pill with left accent indicator)
        self.nav_buttons = {}
        nav_items = [
            ("dashboard",    "Vault Dashboard"),
            ("profiles",     "Biometric Profiles"),
            ("enroll_demo",  "Registration"),
            ("verify_demo",  "Verification"),
        ]
        for nav_id, label in nav_items:
            self._create_nav_item(nav_id, label)

        # BOTTOM PINNED SECTION OF SIDEBAR (Hardware Status Card + Settings + Version)
        self.sidebar_bottom = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        self.sidebar_bottom.pack(side="bottom", fill="x", padx=14, pady=14)

        # Settings Nav Item & Version Info at very bottom
        footer_row = ctk.CTkFrame(self.sidebar_bottom, fg_color="transparent")
        footer_row.pack(side="bottom", fill="x", pady=(10, 0))

        self.settings_btn = ctk.CTkButton(
            footer_row, text="⚙  Settings", anchor="w", height=36, corner_radius=8,
            fg_color=c["nav_active_bg"] if self.active_nav == "settings" else "transparent",
            hover_color=c["card_hover"], text_color=c["text_primary"],
            font=ctk.CTkFont(family=FluentTheme.FONT_FAMILY, size=13),
            command=lambda: self.switch_screen("settings")
        )
        self.settings_btn.pack(side="left", fill="x", expand=True, padx=(0, 8))

        ctk.CTkLabel(
            footer_row, text="v1.0.0",
            font=ctk.CTkFont(family=FluentTheme.FONT_FAMILY, size=11),
            text_color=c["text_muted"]
        ).pack(side="right", padx=4)

        # STATE 2 CLICKABLE HARDWARE STATUS CARD CONTAINER
        self.hw_card_container = ctk.CTkFrame(self.sidebar_bottom, fg_color="transparent")
        self.hw_card_container.pack(side="bottom", fill="x")
        self._refresh_hw_card()

        # RIGHT MAIN VIEWPORT
        self.viewport = ctk.CTkFrame(self.workspace, fg_color=c["canvas_bg"], corner_radius=0)
        self.viewport.pack(side="left", fill="both", expand=True)

        self.switch_screen("dashboard", animate=False, force=True)

    def _create_nav_item(self, nav_id: str, label: str):
        c = self.colors
        is_active = (self.active_nav == nav_id)

        row = ctk.CTkFrame(
            self.sidebar,
            fg_color=c["nav_active_bg"] if is_active else "transparent",
            height=40,
            corner_radius=8
        )
        row.pack(fill="x", padx=12, pady=2)
        row.pack_propagate(False)

        # PowerToys-style vertical accent pill on the left edge when active
        pill = ctk.CTkFrame(
            row, width=4, height=18, corner_radius=2,
            fg_color=self.accent if is_active else "transparent"
        )
        pill.pack(side="left", padx=(6, 10))

        btn = ctk.CTkButton(
            row, text=label, anchor="w", fg_color="transparent", hover_color=c["card_hover"],
            text_color=c["text_primary"] if is_active else c["text_secondary"],
            font=ctk.CTkFont(family=FluentTheme.FONT_FAMILY, size=13, weight="bold" if is_active else "normal"),
            command=lambda nid=nav_id: self.switch_screen(nid)
        )
        btn.pack(side="left", fill="both", expand=True)
        self.nav_buttons[nav_id] = (row, pill, btn)

    # --------------------------------------------------------------------------
    # OPTION B SIDEBAR: STATE 2 EXPANDABLE WEBCAM SELECTOR DRAWER
    # --------------------------------------------------------------------------

    def _refresh_hw_card(self):
        for w in self.hw_card_container.winfo_children():
            w.destroy()

        c = self.colors
        active_dev = self.hw.get_active_device()
        is_ready, _, _ = self.hw.check_readiness()

        card = ctk.CTkFrame(
            self.hw_card_container,
            fg_color=c["card_bg"],
            border_width=1,
            border_color=self.accent if self.webcam_drawer_open else c["card_border"],
            corner_radius=10
        )
        card.pack(fill="x")

        # Header of the Hardware Status Card (Clickable to expand/collapse State 2 Drawer)
        status_symbol = "[ ✔ ] Webcam Online" if is_ready else "[ ✖ ] Camera Unavailable"
        status_color = c["success"] if is_ready else c["danger"]
        chevron = "▴" if self.webcam_drawer_open else "▾"

        header_btn = ctk.CTkButton(
            card,
            text=f"{status_symbol}   {chevron}\n{active_dev['name']}",
            anchor="w",
            height=54,
            corner_radius=8,
            fg_color="transparent",
            hover_color=c["card_hover"],
            text_color=status_color,
            font=ctk.CTkFont(family=FluentTheme.FONT_FAMILY, size=12, weight="bold"),
            command=self._toggle_webcam_drawer
        )
        header_btn._text_label.configure(justify="left")
        header_btn.pack(fill="x", padx=4, pady=4)

        # STATE 2: EXPANDED MULTI-WEBCAM SELECTOR DRAWER
        if self.webcam_drawer_open:
            sep = ctk.CTkFrame(card, fg_color=c["divider"], height=1)
            sep.pack(fill="x", padx=10, pady=(2, 6))

            ctk.CTkLabel(
                card, text="SELECT WEBCAM DEVICE",
                font=ctk.CTkFont(family=FluentTheme.FONT_FAMILY, size=10, weight="bold"),
                text_color=c["text_muted"]
            ).pack(anchor="w", padx=12, pady=(0, 4))

            for dev in self.hw.devices:
                idx = dev["index"]
                selected = (idx == self.hw.active_index)
                st = dev["status"]
                prefix = "(•)" if selected else ("( )" if st == "ONLINE" else "(x)")
                badge = "[ ✔ ]" if st == "ONLINE" else f"[ ✖ {st} ]"
                txt_col = c["text_primary"] if st == "ONLINE" else c["text_muted"]

                dev_btn = ctk.CTkButton(
                    card,
                    text=f"{prefix} {dev['name'].split(':')[0]}  {badge}",
                    anchor="w",
                    height=30,
                    corner_radius=6,
                    fg_color=c["nav_active_bg"] if selected else "transparent",
                    hover_color=c["card_hover"],
                    text_color=txt_col,
                    font=ctk.CTkFont(family=FluentTheme.FONT_FAMILY, size=12),
                    command=lambda i=idx: self._select_webcam_device(i)
                )
                dev_btn.pack(fill="x", padx=8, pady=2)

            # Rescan Button inside Drawer
            rescan_btn = ctk.CTkButton(
                card,
                text="↻  Rescan Devices",
                height=28,
                corner_radius=6,
                fg_color=c["input_bg"],
                hover_color=c["card_hover"],
                text_color=c["text_secondary"],
                font=ctk.CTkFont(family=FluentTheme.FONT_FAMILY, size=11, weight="bold"),
                command=lambda: [self.hw.scan_devices(), self._refresh_hw_card()]
            )
            rescan_btn.pack(fill="x", padx=8, pady=(6, 8))

    def _toggle_webcam_drawer(self):
        self.webcam_drawer_open = not self.webcam_drawer_open
        self._refresh_hw_card()

    def _select_webcam_device(self, index: int):
        self.hw.active_index = index
        self.hw.simulated_hw_state = "ONLINE"
        self._refresh_hw_card()

    # --------------------------------------------------------------------------
    # CUSTOM WINDOW DRAG, MINIMIZE TO SYSTEM TRAY & MAXIMIZE HANDLERS
    # --------------------------------------------------------------------------

    def _start_move(self, event):
        self._drag_x = event.x_root - self.winfo_x()
        self._drag_y = event.y_root - self.winfo_y()

    def _on_move(self, event):
        if getattr(self, "_is_maximized", False) or getattr(self, "is_maximized", False):
            return
        x = event.x_root - getattr(self, "_drag_x", 0)
        y = event.y_root - getattr(self, "_drag_y", 0)
        self.geometry(f"+{x}+{y}")

    def _toggle_maximize(self):
        is_max = getattr(self, "_is_maximized", False)
        if not is_max:
            self._pre_max_geom = self.geometry()
            sw = self.winfo_screenwidth()
            sh = self.winfo_screenheight() - 48
            self.geometry(f"{sw}x{sh}+0+0")
            self._is_maximized = True
            self.is_maximized = True
            if hasattr(self, "max_btn") and self.max_btn.winfo_exists():
                self.max_btn.configure(text="❐")
        else:
            self.geometry(getattr(self, "_pre_max_geom", "1120x700+120+80"))
            self._is_maximized = False
            self.is_maximized = False
            if hasattr(self, "max_btn") and self.max_btn.winfo_exists():
                self.max_btn.configure(text="□")

    def _minimize_window(self):
        self.overrideredirect(False)
        self.iconify()
        self.bind("<Map>", self._on_restore_from_taskbar)

    def _on_restore_from_taskbar(self, event):
        if self.state() == "normal":
            self.overrideredirect(True)
            self.unbind("<Map>")

    def _on_close_button(self):
        if self.minimize_to_tray_var.get():
            ans = messagebox.askyesnocancel(
                "BioVault — Background Tray Mode",
                "Minimize to System Tray is enabled in Settings.\n\n"
                "• Click YES to minimize silently to the background (simulated).\n"
                "• Click NO to quit BioVault completely."
            )
            if ans is True:
                self._minimize_window()
            elif ans is False:
                self.destroy()
        else:
            self.destroy()
    
    # --------------------------------------------------------------------------
    # SCREEN ROUTER & PRE-PROCESS HARDWARE GATE CHECK
    # --------------------------------------------------------------------------

    def _ask_win11_abort_dialog(self, on_confirm_cb):
        """
        Displays a Windows 11 Notepad-style ContentDialog (two-tone card + recessed footer)
        confirming whether the user wants to abort an active camera process.
        """
        c = self.colors
        is_enroll = (self.active_nav == "enroll_demo")

        title_txt = "Abort Biometric Registration?" if is_enroll else "Cancel Biometric Verification?"
        body_txt = (
            "Your webcam is currently active. If you leave now, captured pose samples will be discarded."
            if is_enroll else
            "Your webcam is currently verifying your identity. Leaving now will keep this item locked."
        )

        was_paused = getattr(self, "_ver_timer_paused", False)
        self._ver_timer_paused = True

        dlg = ctk.CTkToplevel(self)
        dlg.title("Confirm")
        dlg.overrideredirect(True)
        dlg.attributes("-topmost", True)
        dlg.configure(fg_color=c["canvas_bg"])

        w, h = 430, 215
        self.update_idletasks()
        x = self.winfo_x() + (self.winfo_width() - w) // 2
        y = self.winfo_y() + (self.winfo_height() - h) // 2
        dlg.geometry(f"{w}x{h}+{x}+{y}")
        dlg.grab_set()

        shell = ctk.CTkFrame(
            dlg, fg_color=c["card_bg"], border_width=1, border_color=c["card_border"], corner_radius=8
        )
        shell.pack(fill="both", expand=True)

        content = ctk.CTkFrame(shell, fg_color="transparent")
        content.pack(side="top", fill="both", expand=True, padx=24, pady=(22, 14))

        ctk.CTkLabel(
            content, text=title_txt,
            font=ctk.CTkFont(family=FluentTheme.FONT_FAMILY, size=18, weight="bold"),
            text_color=c["text_primary"]
        ).pack(anchor="w", pady=(0, 8))

        ctk.CTkLabel(
            content, text=body_txt, justify="left", wraplength=380,
            font=ctk.CTkFont(family=FluentTheme.FONT_FAMILY, size=13),
            text_color=c["text_secondary"]
        ).pack(anchor="w")

        footer = ctk.CTkFrame(shell, fg_color=c["titlebar_bg"], height=66, corner_radius=0)
        footer.pack(side="bottom", fill="x", padx=1, pady=(0, 1))
        footer.pack_propagate(False)

        div = ctk.CTkFrame(shell, fg_color=c["divider"], height=1)
        div.pack(side="bottom", fill="x", padx=1)

        btn_row = ctk.CTkFrame(footer, fg_color="transparent")
        btn_row.pack(fill="both", expand=True, padx=24, pady=15)

        def _on_yes():
            dlg.grab_release()
            dlg.destroy()
            on_confirm_cb()

        def _on_no():
            self._ver_timer_paused = was_paused
            dlg.grab_release()
            dlg.destroy()

        ctk.CTkButton(
            btn_row, text="Yes, Abort", height=34, corner_radius=6,
            fg_color=self.accent, hover_color=self.accent_hover, text_color="#FFFFFF",
            font=ctk.CTkFont(family=FluentTheme.FONT_FAMILY, size=13, weight="bold"),
            command=_on_yes
        ).pack(side="left", fill="x", expand=True, padx=(0, 6))

        ctk.CTkButton(
            btn_row, text="No, Continue", height=34, corner_radius=6,
            fg_color=c["card_bg"], hover_color=c["card_hover"],
            border_width=1, border_color=c["card_border"], text_color=c["text_primary"],
            font=ctk.CTkFont(family=FluentTheme.FONT_FAMILY, size=13),
            command=_on_no
        ).pack(side="right", fill="x", expand=True, padx=(6, 0))

        dlg.bind("<Escape>", lambda e: _on_no())
        dlg.bind("<Return>", lambda e: _on_yes())


    def switch_screen(self, screen_id: str, animate: bool = True, force: bool = False):
        if (
            not force
            and getattr(self, "_cam_running", False)
            and self.active_nav in ("verify_demo", "enroll_demo")
            and screen_id != self.active_nav
        ):
            self._ask_win11_abort_dialog(
                on_confirm_cb=lambda: self.switch_screen(screen_id, animate=animate, force=True)
            )
            return

        if hasattr(self, "_stop_active_camera"):
            self._stop_active_camera()

        if screen_id in ("verify_demo", "enroll_demo"):
            is_ready, _, detail_msg = self.hw.check_readiness()
            if not is_ready:
                self._show_hardware_blocked_modal(target_screen=screen_id, detail_msg=detail_msg)
                return

        self.active_nav = screen_id
        c = self.colors

        # Update sidebar nav highlight states
        for nid, (row, pill, btn) in self.nav_buttons.items():
            active = (nid == screen_id)
            row.configure(fg_color=c["nav_active_bg"] if active else "transparent")
            pill.configure(fg_color=self.accent if active else "transparent")
            btn.configure(
                text_color=c["text_primary"] if active else c["text_secondary"],
                font=ctk.CTkFont(family=FluentTheme.FONT_FAMILY, size=13, weight="bold" if active else "normal")
            )

        self.settings_btn.configure(
            fg_color=c["nav_active_bg"] if screen_id == "settings" else "transparent"
        )

        if hasattr(self, "_nav_anim_after_id") and self._nav_anim_after_id:
            try:
                self.after_cancel(self._nav_anim_after_id)
            except Exception:
                pass
            self._nav_anim_after_id = None

        outer_vp = getattr(self, "_outer_viewport", self.viewport)
        for child in outer_vp.winfo_children():
            child.destroy()

        self._outer_viewport = outer_vp
        page_frame = ctk.CTkFrame(outer_vp, fg_color=c["canvas_bg"], corner_radius=0)
        self.viewport = page_frame

        if screen_id == "dashboard":
            self._render_dashboard_screen()
        elif screen_id == "profiles":
            self._render_profiles_screen()
        elif screen_id == "settings":
            self._render_settings_screen()
        elif screen_id == "enroll_demo":
            self._render_registration_screen()
        elif screen_id == "verify_demo":
            self._render_verification_screen()

        if animate:
            # Place off-offset first and force layout calculation so frame 1 is immediately visible
            page_frame.place(x=0, y=42, relwidth=1.0, relheight=1.0)
            page_frame.update_idletasks()
            self._run_entrance_transition(page_frame, step=0, total_steps=10)
        else:
            page_frame.pack(fill="both", expand=True)

    def _run_entrance_transition(self, page_frame: ctk.CTkFrame, step: int, total_steps: int):
        if not page_frame.winfo_exists():
            return
        if step >= total_steps:
            page_frame.place_forget()
            page_frame.pack(fill="both", expand=True)
            self._nav_anim_after_id = None
            return

        # Smooth Cubic-Out curve from y=42px -> y=0px over ~140ms
        progress = (step + 1) / float(total_steps)
        eased = 1.0 - ((1.0 - progress) ** 3)
        y_offset = int(round(42 * (1.0 - eased)))

        page_frame.place_configure(y=y_offset)
        self._nav_anim_after_id = self.after(
            14, lambda: self._run_entrance_transition(page_frame, step + 1, total_steps)
        )


    # --------------------------------------------------------------------------
    # HARDWARE READINESS CHECK MODAL (Blocks Scan if Webcam is Busy / Covered)
    # --------------------------------------------------------------------------

    def _show_hardware_blocked_modal(self, target_screen: str, detail_msg: str):
        c = self.colors
        modal = ctk.CTkToplevel(self)
        modal.title("BioVault — Hardware Readiness Check")
        modal.geometry("500x410")
        modal.resizable(False, False)
        modal.attributes("-topmost", True)
        modal.configure(fg_color=c["canvas_bg"])
        modal.grab_set()

        card = ctk.CTkFrame(
            modal, fg_color=c["card_bg"], border_width=1, border_color=c["danger"], corner_radius=12
        )
        card.pack(fill="both", expand=True, padx=22, pady=22)

        ctk.CTkLabel(
            card, text="[ ✖ ]  WEBCAM NOT AVAILABLE",
            font=ctk.CTkFont(family=FluentTheme.FONT_FAMILY, size=18, weight="bold"),
            text_color=c["danger"]
        ).pack(pady=(22, 6))

        dev = self.hw.get_active_device()
        ctk.CTkLabel(
            card, text=f"Selected Device:  {dev['name']}",
            font=ctk.CTkFont(family=FluentTheme.FONT_FAMILY, size=13, weight="bold"),
            text_color=c["text_primary"]
        ).pack(pady=(0, 12))

        diag_box = ctk.CTkFrame(card, fg_color=c["input_bg"], corner_radius=8)
        diag_box.pack(fill="x", padx=24, pady=6)

        ctk.CTkLabel(
            diag_box,
            text=(
                f"• Device Detected:       [ ✔ ] Yes\n"
                f"• Stream Accessible:     [ ✖ ] Blocked / Unavailable\n\n"
                f"Diagnostic Detail:\n{detail_msg}"
            ),
            justify="left",
            wraplength=400,
            font=ctk.CTkFont(family=FluentTheme.FONT_FAMILY, size=12),
            text_color=c["text_secondary"]
        ).pack(anchor="w", padx=16, pady=14)

        btn_row = ctk.CTkFrame(card, fg_color="transparent")
        btn_row.pack(fill="x", padx=24, pady=(16, 10))

        def _fix_and_retry():
            self.hw.simulated_hw_state = "ONLINE"
            self.hw.devices[self.hw.active_index]["status"] = "ONLINE"
            self._refresh_hw_card()
            modal.destroy()
            self.switch_screen(target_screen)

        ctk.CTkButton(
            btn_row, text="↻  Retry Check (Clear Lock)", height=36,
            fg_color=self.accent, hover_color=self.accent_hover,
            font=ctk.CTkFont(family=FluentTheme.FONT_FAMILY, size=13, weight="bold"),
            command=_fix_and_retry
        ).pack(side="left", fill="x", expand=True, padx=(0, 8))

        ctk.CTkButton(
            btn_row, text="Cancel", width=100, height=36,
            fg_color=c["card_hover"], text_color=c["text_primary"],
            command=modal.destroy
        ).pack(side="right")

        if target_screen == "verify_demo":
            kb_icon = create_keyboard_only_icon()
            ctk.CTkButton(
                card,
                text="  Use Emergency Recovery Password Instead",
                image=kb_icon,
                compound="left",
                height=36,
                fg_color=c["input_bg"],
                hover_color=c["card_hover"],
                text_color=c["text_primary"],
                command=lambda: [modal.destroy(), self._open_mock_password_dialog()]
            ).pack(fill="x", padx=24, pady=(4, 14))

    # --------------------------------------------------------------------------
    # SCREEN 1: VAULT DASHBOARD (PowerToys-style Fluent Cards & Spacing)
    # --------------------------------------------------------------------------

    def _set_sim_hw_state(self, state_code: str):
        self.hw.simulated_hw_state = state_code
        self._refresh_hw_card()
        # Clear viewport completely before re-rendering so it never duplicates/mirrors the dashboard!
        self.switch_screen("dashboard", animate=False, force=True)

    def _render_dashboard_screen(self):
        for w in self.viewport.winfo_children():
            w.destroy()

        c = self.colors
        has_profiles = len(self.mock_users) > 0
        is_authed = bool(self.active_user)

        # Strictly filter locked items so the logged-in profile ONLY sees their own files!
        user_items = [
            it for it in self.mock_locked_items
            if is_authed and it.get("owner", "").lower() == self.active_user.lower()
        ]

        scroll = ctk.CTkScrollableFrame(self.viewport, fg_color=c["canvas_bg"], corner_radius=0)
        scroll.pack(fill="both", expand=True, padx=34, pady=(20, 24))

        # Top Header Row
        top_row = ctk.CTkFrame(scroll, fg_color="transparent")
        top_row.pack(fill="x", pady=(0, 20))

        title_col = ctk.CTkFrame(top_row, fg_color="transparent")
        title_col.pack(side="left")
        ctk.CTkLabel(
            title_col, text="Vault Dashboard",
            font=ctk.CTkFont(family="Segoe UI", size=28, weight="bold"),
            text_color=c["text_primary"]
        ).pack(anchor="w")

        profile_count = len(self.mock_users)
        profile_lbl = f"{profile_count} Enrolled Profile" if profile_count == 1 else f"{profile_count} Enrolled Profiles"
        if not has_profiles:
            items_lbl = "Setup Required"
        elif not is_authed:
            items_lbl = "Locked Items Hidden (Unverified)"
        else:
            items_lbl = f"Active Profile: {self.active_user}   •   {len(user_items)} Locked Items"

        ctk.CTkLabel(
            title_col,
            text=f"{items_lbl}   •   {profile_lbl}",
            font=ctk.CTkFont(family=FluentTheme.FONT_FAMILY, size=13),
            text_color=c["text_secondary"]
        ).pack(anchor="w", pady=(2, 0))

        # Primary Action Buttons on Right
        act_col = ctk.CTkFrame(top_row, fg_color="transparent")
        act_col.pack(side="right", pady=6)

        can_lock = has_profiles and is_authed
        if is_authed:
            ctk.CTkButton(
                act_col, text="Switch User", width=105, height=38, corner_radius=8,
                fg_color="transparent", hover_color=c["card_hover"],
                border_width=1, border_color=c["card_border"], text_color=c["text_secondary"],
                font=ctk.CTkFont(family=FluentTheme.FONT_FAMILY, size=12, weight="bold"),
                command=self._logout_current_session
            ).pack(side="right", padx=(10, 0))

        ctk.CTkButton(
            act_col, text="+ Lock File", width=120, height=38, corner_radius=8,
            state="normal" if can_lock else "disabled",
            fg_color=c["card_bg"], hover_color=c["card_hover"],
            border_width=1, border_color=c["card_border"], text_color=c["text_primary"],
            font=ctk.CTkFont(family=FluentTheme.FONT_FAMILY, size=13, weight="bold"),
            command=lambda: self._prompt_lock_item(is_dir=False)
        ).pack(side="right", padx=(10, 0))

        ctk.CTkButton(
            act_col, text="+ Lock Folder", width=135, height=38, corner_radius=8,
            state="normal" if can_lock else "disabled",
            fg_color=self.accent if can_lock else c["input_bg"],
            hover_color=self.accent_hover, text_color="#FFFFFF",
            font=ctk.CTkFont(family=FluentTheme.FONT_FAMILY, size=13, weight="bold"),
            command=lambda: self._prompt_lock_item(is_dir=True)
        ).pack(side="right")

        ctk.CTkLabel(
            scroll, text="Protected items",
            font=ctk.CTkFont(family="Segoe UI", size=16, weight="bold"),
            text_color=c["text_primary"]
        ).pack(anchor="w", pady=(4, 12))

        # --- STATE 0: INITIAL STATE (NO PROFILE REGISTERED YET) ---
        if not has_profiles:
            onboarding_card = ctk.CTkFrame(
                scroll, fg_color=c["card_bg"], border_width=1, border_color=c["card_border"], corner_radius=12
            )
            onboarding_card.pack(fill="both", expand=True, pady=(30, 10))

            ctk.CTkLabel(
                onboarding_card,
                text="First register a profile to get started",
                font=ctk.CTkFont(family="Segoe UI", size=20, weight="bold"),
                text_color=c["text_primary"], justify="center"
            ).pack(pady=(54, 8))

            ctk.CTkLabel(
                onboarding_card,
                text="Enroll your biometric face & ocular template before locking files or folders.",
                font=ctk.CTkFont(family=FluentTheme.FONT_FAMILY, size=13),
                text_color=c["text_secondary"], justify="center"
            ).pack(padx=24, pady=(0, 22))

            ctk.CTkButton(
                onboarding_card, text="+ Register Biometric Profile", width=220, height=40, corner_radius=8,
                fg_color=self.accent, hover_color=self.accent_hover, text_color="#FFFFFF",
                font=ctk.CTkFont(family=FluentTheme.FONT_FAMILY, size=13, weight="bold"),
                command=lambda: self.switch_screen("enroll_demo")
            ).pack(pady=(0, 54))
            return

        # --- STATE 1: PROFILE EXISTS, USER NOT VERIFIED -> IN-WINDOW ERROR CARD ---
        if not is_authed:
            auth_card = ctk.CTkFrame(
                scroll, fg_color=c["card_bg"], border_width=1, border_color=c["danger"], corner_radius=12
            )
            auth_card.pack(fill="x", pady=10)

            ctk.CTkLabel(
                auth_card,
                text="[ ✖ ]  Cannot view locked files without authentication",
                font=ctk.CTkFont(family="Segoe UI", size=16, weight="bold"),
                text_color=c["danger"]
            ).pack(pady=(28, 6))

            ctk.CTkLabel(
                auth_card,
                text="Verify your biometric identity to view files locked under your profile,\nor register a new profile to create your own personal vault.",
                font=ctk.CTkFont(family=FluentTheme.FONT_FAMILY, size=13),
                text_color=c["text_secondary"], justify="center"
            ).pack(padx=24, pady=(0, 18))

            btn_row = ctk.CTkFrame(auth_card, fg_color="transparent")
            btn_row.pack(pady=(0, 26))

            ctk.CTkButton(
                btn_row, text="Verify with Face ID", width=165, height=38, corner_radius=8,
                fg_color=self.accent, hover_color=self.accent_hover, text_color="#FFFFFF",
                font=ctk.CTkFont(family=FluentTheme.FONT_FAMILY, size=13, weight="bold"),
                command=self._start_startup_verification
            ).pack(side="left", padx=5)

            ctk.CTkButton(
                btn_row, text="Use Recovery Password", width=175, height=38, corner_radius=8,
                fg_color=c["input_bg"], hover_color=c["card_hover"],
                border_width=1, border_color=c["card_border"], text_color=c["text_primary"],
                font=ctk.CTkFont(family=FluentTheme.FONT_FAMILY, size=13, weight="bold"),
                command=lambda: self._show_inline_dashboard_password(auth_card)
            ).pack(side="left", padx=5)

            ctk.CTkButton(
                btn_row, text="+ Register New Profile", width=175, height=38, corner_radius=8,
                fg_color="transparent", hover_color=c["card_hover"],
                border_width=1, border_color=c["card_border"], text_color=c["text_primary"],
                font=ctk.CTkFont(family=FluentTheme.FONT_FAMILY, size=13, weight="bold"),
                command=lambda: self.switch_screen("enroll_demo")
            ).pack(side="left", padx=5)
            return

        # --- LIVE AUTO-RELOCK COUNTDOWN BANNER (WHEN ITEMS ARE TEMPORARILY UNLOCKED) ---
        if self.unlock_lease_remaining_sec > 0:
            lease_bar = ctk.CTkFrame(
                scroll, fg_color=c["card_bg"], border_width=1, border_color=c["success"], corner_radius=10
            )
            lease_bar.pack(fill="x", pady=(0, 12))
            mins, secs = divmod(self.unlock_lease_remaining_sec, 60)
            self.lease_countdown_lbl = ctk.CTkLabel(
                lease_bar,
                text=f"🔓  All items for '{self.active_user}' are unlocked   •   Auto-relocking in {mins:02d}:{secs:02d}",
                font=ctk.CTkFont(family=FluentTheme.FONT_FAMILY, size=13, weight="bold"),
                text_color=c["success"]
            )
            self.lease_countdown_lbl.pack(side="left", padx=18, pady=10)

            ctk.CTkButton(
                lease_bar, text="Relock Now", width=110, height=28, corner_radius=6,
                fg_color=c["danger"], hover_color=c["card_hover"], text_color="#FFFFFF",
                font=ctk.CTkFont(family=FluentTheme.FONT_FAMILY, size=12, weight="bold"),
                command=self._relock_user_items_now
            ).pack(side="right", padx=14, pady=8)

        # --- STATE 2: VERIFIED, NO ITEMS LOCKED BY THIS PROFILE YET ---
        if not user_items:
            empty_card = ctk.CTkFrame(
                scroll, fg_color=c["card_bg"], border_width=1, border_color=c["card_border"], corner_radius=12
            )
            empty_card.pack(fill="x", pady=10)
            ctk.CTkLabel(
                empty_card,
                text=f"No files or folders are currently locked under profile '{self.active_user}'.\nClick '+ Lock Folder' or '+ Lock File' above to protect an item.",
                font=ctk.CTkFont(family=FluentTheme.FONT_FAMILY, size=13),
                text_color=c["text_secondary"], justify="center"
            ).pack(padx=24, pady=36)
        else:
            # --- STATE 3: VERIFIED -> SHOW ONLY THIS PROFILE'S LOCKED FILES ---
            for item in user_items:
                self._create_vault_item_card(scroll, item)

    def _logout_current_session(self):
        """Re-locks any temporarily unlocked files for the active user and ends the session."""
        self._stop_active_camera()
        if self.active_user:
            self.vault.relock_all_for_owner(self.active_user)
            self.mock_locked_items = self.vault.state["locked_items"]
        self.unlock_lease_remaining_sec = 0
        self.active_user = None
        self.session_authenticated = False
        self._current_unlock_target = None
        self.switch_screen("dashboard", animate=False, force=True)

    def _trigger_user_batch_unlock(self, item: dict | None = None):
        """
        Since the user is already authenticated in their session, clicking Unlock on any file
        unlocks ALL files/folders in their name for `self.auto_relock_minutes` minutes.
        """
        if not self.active_user:
            self._start_startup_verification()
            return

        self.vault.unlock_all_for_owner(self.active_user)
        self.mock_locked_items = self.vault.state["locked_items"]
        self.unlock_lease_remaining_sec = max(1, int(self.auto_relock_minutes)) * 60

        # Start 1-second lease countdown
        job = getattr(self, "_lease_timer_job", None)
        if job is not None:
            try:
                self.after_cancel(str(job))
            except Exception:
                pass
            self._lease_timer_job = None
        self._tick_unlock_lease_timer()

        # If user clicked Unlock on a specific folder/file, optionally open it in Explorer
        if item and os.path.exists(item["path"]):
            try:
                os.startfile(item["path"])
            except Exception:
                pass

        self.switch_screen("dashboard", animate=False, force=True)

    def _relock_user_items_now(self):
        """Manually ends the temporary unlock lease and re-applies NTFS locks immediately."""
        job = getattr(self, "_lease_timer_job", None)
        if job is not None:
            try:
                self.after_cancel(str(job))
            except Exception:
                pass
            self._lease_timer_job = None

        self.unlock_lease_remaining_sec = 0
        if self.active_user:
            self.vault.relock_all_for_owner(self.active_user)
            self.mock_locked_items = self.vault.state["locked_items"]

        if self.active_nav == "dashboard":
            self.switch_screen("dashboard", animate=False, force=True)

    def _tick_unlock_lease_timer(self):
        """Counts down the temporary unlock lease and auto-relocks when time expires."""
        if self.unlock_lease_remaining_sec <= 0 or not self.active_user:
            self._relock_user_items_now()
            return

        mins, secs = divmod(self.unlock_lease_remaining_sec, 60)
        lbl = self.lease_countdown_lbl
        if lbl is not None and lbl.winfo_exists():
            lbl.configure(
                text=f"🔓  All items for '{self.active_user}' are unlocked   •   Auto-relocking in {mins:02d}:{secs:02d}"
            )

        self.unlock_lease_remaining_sec -= 1
        self._lease_timer_job = self.after(1000, self._tick_unlock_lease_timer)

    def _start_startup_verification(self):
        """Routes to the in-window Biometric Verification screen for open profile login."""
        self._current_unlock_target = None
        self._verify_mode_purpose = "APP_STARTUP"
        self.switch_screen("verify_demo")

    def _show_inline_dashboard_password(self, parent_card: ctk.CTkFrame):
        """Expands an inline recovery password bar with a profile selector inside the same window."""
        if hasattr(self, "_inline_pwd_box") and self._inline_pwd_box.winfo_exists():
            return

        c = self.colors
        self._inline_pwd_box = ctk.CTkFrame(parent_card, fg_color=c["input_bg"], corner_radius=8)
        self._inline_pwd_box.pack(fill="x", padx=40, pady=(0, 20))

        row = ctk.CTkFrame(self._inline_pwd_box, fg_color="transparent")
        row.pack(fill="x", padx=14, pady=12)

        profile_names = [u.get("username", u.get("name", "Owner")) for u in self.mock_users] or ["Owner"]
        user_picker = ctk.CTkOptionMenu(
            row, values=profile_names, width=135, height=34,
            fg_color=c["card_bg"], button_color=self.accent,
            button_hover_color=self.accent_hover, text_color=c["text_primary"],
            font=ctk.CTkFont(family=FluentTheme.FONT_FAMILY, size=12, weight="bold")
        )
        user_picker.pack(side="left", padx=(0, 8))

        pwd_entry = ctk.CTkEntry(
            row, show="*", height=34,
            placeholder_text="Enter Emergency Recovery Password...",
            font=ctk.CTkFont(family=FluentTheme.FONT_FAMILY, size=13)
        )
        pwd_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))
        pwd_entry.focus_set()

        err_lbl = ctk.CTkLabel(
            self._inline_pwd_box, text="",
            font=ctk.CTkFont(family=FluentTheme.FONT_FAMILY, size=12),
            text_color=c["danger"]
        )

        def _verify_inline():
            if self.vault.verify_recovery_password(pwd_entry.get().strip()):
                self.active_user = user_picker.get()
                self.session_authenticated = True
                self.switch_screen("dashboard", animate=True, force=True)
            else:
                err_lbl.configure(text="[ ✖ ] Incorrect recovery password.")
                err_lbl.pack(pady=(0, 8))

        ctk.CTkButton(
            row, text="Unlock Session", width=135, height=34, corner_radius=6,
            fg_color=self.accent, hover_color=self.accent_hover, text_color="#FFFFFF",
            font=ctk.CTkFont(family=FluentTheme.FONT_FAMILY, size=12, weight="bold"),
            command=_verify_inline
        ).pack(side="right")

        pwd_entry.bind("<Return>", lambda e: _verify_inline())

    def _create_vault_item_card(self, parent, item: dict):
        c = self.colors
        is_unlocked = (item.get("status") == "unlocked") and (self.unlock_lease_remaining_sec > 0)

        card = ctk.CTkFrame(
            parent, fg_color=c["card_bg"], border_width=1,
            border_color=c["success"] if is_unlocked else c["card_border"], corner_radius=12
        )
        card.pack(fill="x", pady=6)

        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="x", padx=20, pady=14)

        item_icon = create_win11_item_icon(is_dir=item.get("is_dir", True), size=(40, 40))
        icon_lbl = ctk.CTkLabel(inner, text="", image=item_icon, width=46)
        icon_lbl.image = item_icon
        icon_lbl.pack(side="left", padx=(0, 14))

        info_col = ctk.CTkFrame(inner, fg_color="transparent")
        info_col.pack(side="left", fill="x", expand=True)

        status_tag = "  [ 🔓 UNLOCKED ]" if is_unlocked else "  [ 🔒 LOCKED ]"
        ctk.CTkLabel(
            info_col, text=f"{item['name']}{status_tag}",
            font=ctk.CTkFont(family="Segoe UI", size=15, weight="bold"),
            text_color=c["success"] if is_unlocked else c["text_primary"]
        ).pack(anchor="w")

        ctk.CTkLabel(
            info_col, text=item["path"],
            font=ctk.CTkFont(family=FluentTheme.FONT_FAMILY, size=12),
            text_color=c["text_secondary"]
        ).pack(anchor="w", pady=(2, 3))

        ctk.CTkLabel(
            info_col,
            text=f"Owner Profile: {item['owner']}   •   Locked: {item.get('locked_at', item.get('date', 'Protected'))}",
            font=ctk.CTkFont(family=FluentTheme.FONT_FAMILY, size=12),
            text_color=c["text_muted"]
        ).pack(anchor="w")

        ctk.CTkButton(
            inner, text="Remove Lock", width=105, height=36, corner_radius=8,
            fg_color="transparent", hover_color=c["card_hover"],
            border_width=1, border_color=c["card_border"], text_color=c["text_secondary"],
            font=ctk.CTkFont(family=FluentTheme.FONT_FAMILY, size=12),
            command=lambda it=item: [
                self.vault.remove_item_permanently(it["path"]),
                setattr(self, "mock_locked_items", self.vault.state["locked_items"]),
                self.switch_screen("dashboard", animate=False, force=True)
            ]
        ).pack(side="right", padx=(8, 0))

        if is_unlocked:
            ctk.CTkButton(
                inner, text="Open", width=115, height=36, corner_radius=8,
                fg_color=c["success"], hover_color=self.accent_hover, text_color="#FFFFFF",
                font=ctk.CTkFont(family=FluentTheme.FONT_FAMILY, size=13, weight="bold"),
                command=lambda p=item["path"]: os.startfile(p) if os.path.exists(p) else None
            ).pack(side="right", padx=(16, 0))
        else:
            ctk.CTkButton(
                inner, text="Unlock", width=115, height=36, corner_radius=8,
                fg_color=self.accent, hover_color=self.accent_hover, text_color="#FFFFFF",
                font=ctk.CTkFont(family=FluentTheme.FONT_FAMILY, size=13, weight="bold"),
                command=lambda it=item: self._start_unlock_for_item(it)
            ).pack(side="right", padx=(16, 0))


    def _prompt_lock_item(self, is_dir: bool):
        if not self.active_user:
            messagebox.showwarning("Authentication Required", "Please log into your profile before locking items.")
            return

        path = (
            filedialog.askdirectory(title="Select Folder to Lock with BioVault")
            if is_dir else
            filedialog.askopenfilename(title="Select File to Lock with BioVault")
        )
        if not path:
            return

        if not self.vault.has_recovery_password():
            self._prompt_initial_recovery_password(
                on_ready=lambda: self._execute_real_lock(path)
            )
        else:
            self._execute_real_lock(path)

    def _execute_real_lock(self, path: str):
        owner = self.active_user or (self.mock_users[0]["username"] if self.mock_users else "Owner")
        ok, msg = self.vault.lock_path_ntfs(path, owner_name=owner)
        if not ok:
            messagebox.showerror("BioVault Lock Error", msg)
        self.mock_locked_items = self.vault.state["locked_items"]
        self.switch_screen("dashboard", animate=False, force=True)

    def _prompt_initial_recovery_password(self, on_ready):
        c = self.colors
        dlg = ctk.CTkToplevel(self)
        dlg.title("Set Emergency Recovery Password")
        dlg.geometry("420x250")
        dlg.resizable(False, False)
        dlg.attributes("-topmost", True)
        dlg.configure(fg_color=c["canvas_bg"])
        dlg.grab_set()

        ctk.CTkLabel(
            dlg, text="Set Emergency Recovery Password",
            font=ctk.CTkFont(family="Segoe UI", size=16, weight="bold"),
            text_color=c["text_primary"]
        ).pack(pady=(20, 4))

        ctk.CTkLabel(
            dlg, text="Required once before locking files so you never get locked out.",
            font=ctk.CTkFont(family=FluentTheme.FONT_FAMILY, size=12),
            text_color=c["text_secondary"]
        ).pack(pady=(0, 12))

        e1 = ctk.CTkEntry(dlg, show="*", width=320, height=34, placeholder_text="Create recovery password (min 4 chars)...")
        e1.pack(pady=4)
        e2 = ctk.CTkEntry(dlg, show="*", width=320, height=34, placeholder_text="Confirm recovery password...")
        e2.pack(pady=4)
        e1.focus_set()

        def _save_pwd():
            p1, p2 = e1.get().strip(), e2.get().strip()
            if len(p1) < 4:
                messagebox.showwarning("BioVault", "Password must be at least 4 characters.", parent=dlg)
                return
            if p1 != p2:
                messagebox.showerror("BioVault", "Passwords do not match.", parent=dlg)
                return
            self.vault.set_recovery_password(p1)
            dlg.destroy()
            on_ready()

        btn_row = ctk.CTkFrame(dlg, fg_color="transparent")
        btn_row.pack(fill="x", padx=50, pady=14)
        ctk.CTkButton(
            btn_row, text="Cancel", width=110, fg_color=c["card_hover"],
            text_color=c["text_primary"], command=dlg.destroy
        ).pack(side="left")
        ctk.CTkButton(
            btn_row, text="Save & Lock", width=150, fg_color=self.accent,
            hover_color=self.accent_hover, text_color="#FFFFFF", command=_save_pwd
        ).pack(side="right")

    def _open_mock_password_dialog(self):
        """Rebuilt Emergency Recovery Password Dialog with visible Verify button and Enter key binding."""
        c = self.colors
        target_item = getattr(self, "_current_unlock_target", None)

        dlg = ctk.CTkToplevel(self)
        dlg.title("BioVault — Emergency Recovery Password")
        w, h = 460, 340
        self.update_idletasks()
        x = self.winfo_x() + (self.winfo_width() - w) // 2
        y = self.winfo_y() + (self.winfo_height() - h) // 2
        dlg.geometry(f"{w}x{h}+{x}+{y}")
        dlg.resizable(False, False)
        dlg.attributes("-topmost", True)
        dlg.configure(fg_color=c["canvas_bg"])
        dlg.grab_set()

        card = ctk.CTkFrame(
            dlg, fg_color=c["card_bg"], border_width=1, border_color=c["card_border"], corner_radius=12
        )
        card.pack(fill="both", expand=True, padx=16, pady=16)

        ctk.CTkLabel(
            card, text="Emergency Recovery Password",
            font=ctk.CTkFont(family="Segoe UI", size=18, weight="bold"),
            text_color=c["text_primary"]
        ).pack(anchor="w", padx=24, pady=(20, 4))

        ctk.CTkLabel(
            card, text="Select your profile and enter your recovery password to unlock:",
            font=ctk.CTkFont(family=FluentTheme.FONT_FAMILY, size=12),
            text_color=c["text_secondary"]
        ).pack(anchor="w", padx=24, pady=(0, 12))

        profile_names = [u.get("username", u.get("name", "Owner")) for u in self.mock_users] or ["Owner"]
        default_user = target_item["owner"] if target_item else (self.active_user or profile_names[0])

        user_picker = ctk.CTkOptionMenu(
            card, values=profile_names, height=34,
            fg_color=c["input_bg"], button_color=self.accent,
            button_hover_color=self.accent_hover, text_color=c["text_primary"],
            font=ctk.CTkFont(family=FluentTheme.FONT_FAMILY, size=13, weight="bold")
        )
        if default_user in profile_names:
            user_picker.set(default_user)
        user_picker.pack(fill="x", padx=24, pady=(0, 10))

        entry = ctk.CTkEntry(
            card, show="*", height=38,
            placeholder_text="Type recovery password and press Enter...",
            font=ctk.CTkFont(family=FluentTheme.FONT_FAMILY, size=13)
        )
        entry.pack(fill="x", padx=24, pady=(0, 6))

        status_lbl = ctk.CTkLabel(
            card, text="", height=20,
            font=ctk.CTkFont(family=FluentTheme.FONT_FAMILY, size=12, weight="bold"),
            text_color=c["danger"]
        )
        status_lbl.pack(fill="x", padx=24, pady=(0, 8))

        def _submit_password(event=None):
            pwd = entry.get().strip()
            if not pwd:
                status_lbl.configure(text="[ ✖ ] Please enter your recovery password.")
                return
            if not self.vault.verify_recovery_password(pwd):
                status_lbl.configure(text="[ ✖ ] Incorrect recovery password.")
                return

            selected_user = user_picker.get()
            dlg.grab_release()
            dlg.destroy()

            self._stop_active_camera()
            self.active_user = selected_user
            self.session_authenticated = True

            if getattr(self, "_verify_mode_purpose", "ITEM_UNLOCK") == "ITEM_UNLOCK":
                self._verify_mode_purpose = "ITEM_UNLOCK"
                self._trigger_user_batch_unlock(target_item)
                return

            self._verify_mode_purpose = "ITEM_UNLOCK"
            self.mock_locked_items = self.vault.state["locked_items"]
            self.switch_screen("dashboard", animate=True, force=True)

        # Pack the action buttons at the bottom so they are ALWAYS visible
        btn_row = ctk.CTkFrame(card, fg_color="transparent")
        btn_row.pack(side="bottom", fill="x", padx=24, pady=(4, 18))

        ctk.CTkButton(
            btn_row, text="Cancel", width=115, height=38, corner_radius=8,
            fg_color=c["input_bg"], hover_color=c["card_hover"],
            border_width=1, border_color=c["card_border"], text_color=c["text_primary"],
            font=ctk.CTkFont(family=FluentTheme.FONT_FAMILY, size=13),
            command=dlg.destroy
        ).pack(side="left")

        ctk.CTkButton(
            btn_row, text="Verify & Unlock", height=38, corner_radius=8,
            fg_color=self.accent, hover_color=self.accent_hover, text_color="#FFFFFF",
            font=ctk.CTkFont(family=FluentTheme.FONT_FAMILY, size=13, weight="bold"),
            command=_submit_password
        ).pack(side="right", fill="x", expand=True, padx=(10, 0))

        # Bind Enter (<Return> and numpad <KP_Enter>) on both entry and dialog
        entry.bind("<Return>", _submit_password)
        dlg.bind("<Return>", _submit_password)
        dlg.bind("<Escape>", lambda e: dlg.destroy())
        dlg.after(80, entry.focus_force)

    def _start_unlock_for_item(self, item: dict):
        self._current_unlock_target = item
        self._verify_mode_purpose = "ITEM_UNLOCK"
        self.switch_screen("verify_demo")
    


    # --------------------------------------------------------------------------
    # SCREEN 2: BIOMETRIC PROFILES
    # --------------------------------------------------------------------------

    def _render_profiles_screen(self):
        for w in self.viewport.winfo_children():
            w.destroy()

        c = self.colors
        has_profiles = len(self.mock_users) > 0
        is_authed = getattr(self, "session_authenticated", True)

        scroll = ctk.CTkScrollableFrame(self.viewport, fg_color=c["canvas_bg"], corner_radius=0)
        scroll.pack(fill="both", expand=True, padx=34, pady=(20, 24))

        top_row = ctk.CTkFrame(scroll, fg_color="transparent")
        top_row.pack(fill="x", pady=(0, 20))

        title_col = ctk.CTkFrame(top_row, fg_color="transparent")
        title_col.pack(side="left")
        ctk.CTkLabel(
            title_col, text="Biometric Profiles",
            font=ctk.CTkFont(family="Segoe UI", size=28, weight="bold"),
            text_color=c["text_primary"]
        ).pack(anchor="w")
        ctk.CTkLabel(
            title_col,
            text="512-D ArcFace Identity Embeddings   •   4-Ratio Ocular Geometry   •   3-Region POS rPPG Liveness",
            font=ctk.CTkFont(family=FluentTheme.FONT_FAMILY, size=13),
            text_color=c["text_secondary"]
        ).pack(anchor="w", pady=(2, 0))

        # Allow enrollment if no profiles exist yet OR if the current session is authenticated
        can_enroll = (not has_profiles) or is_authed
        ctk.CTkButton(
            top_row, text="+ Enroll New Profile", width=165, height=38, corner_radius=8,
            state="normal" if can_enroll else "disabled",
            fg_color=self.accent if can_enroll else c["input_bg"],
            hover_color=self.accent_hover, text_color="#FFFFFF",
            font=ctk.CTkFont(family=FluentTheme.FONT_FAMILY, size=13, weight="bold"),
            command=lambda: self.switch_screen("enroll_demo")
        ).pack(side="right", pady=6)

        # --- BLOCK VIEWING/DELETING PROFILES IF LOCKED ---
        if has_profiles and not is_authed:
            auth_card = ctk.CTkFrame(
                scroll, fg_color=c["card_bg"], border_width=1, border_color=c["danger"], corner_radius=12
            )
            auth_card.pack(fill="x", pady=10)

            ctk.CTkLabel(
                auth_card,
                text="[ ✖ ]  Cannot view or modify biometric profiles without authentication",
                font=ctk.CTkFont(family="Segoe UI", size=16, weight="bold"),
                text_color=c["danger"]
            ).pack(pady=(28, 6))

            ctk.CTkLabel(
                auth_card,
                text="Authenticate your session first to view enrolled users, add new profiles, or delete existing templates.",
                font=ctk.CTkFont(family=FluentTheme.FONT_FAMILY, size=13),
                text_color=c["text_secondary"], justify="center"
            ).pack(padx=24, pady=(0, 18))

            btn_row = ctk.CTkFrame(auth_card, fg_color="transparent")
            btn_row.pack(pady=(0, 26))

            ctk.CTkButton(
                btn_row, text="Verify with Face ID", width=175, height=38, corner_radius=8,
                fg_color=self.accent, hover_color=self.accent_hover, text_color="#FFFFFF",
                font=ctk.CTkFont(family=FluentTheme.FONT_FAMILY, size=13, weight="bold"),
                command=self._start_startup_verification
            ).pack(side="left", padx=6)

            ctk.CTkButton(
                btn_row, text="Use Recovery Password", width=185, height=38, corner_radius=8,
                fg_color=c["input_bg"], hover_color=c["card_hover"],
                border_width=1, border_color=c["card_border"], text_color=c["text_primary"],
                font=ctk.CTkFont(family=FluentTheme.FONT_FAMILY, size=13, weight="bold"),
                command=lambda: self._show_inline_dashboard_password(auth_card)
            ).pack(side="left", padx=6)
            return

        # --- EMPTY PROFILES STATE ---
        if not has_profiles:
            empty_card = ctk.CTkFrame(
                scroll, fg_color=c["card_bg"], border_width=1, border_color=c["card_border"], corner_radius=12
            )
            empty_card.pack(fill="x", pady=14)
            ctk.CTkLabel(
                empty_card,
                text="No biometric profiles enrolled yet.\nClick '+ Enroll New Profile' above to start the 5-step guided registration.",
                font=ctk.CTkFont(family=FluentTheme.FONT_FAMILY, size=13),
                text_color=c["text_secondary"], justify="center"
            ).pack(padx=24, pady=40)
            return

        # --- ENROLLED PROFILE CARDS ---
        for u in self.mock_users:
            card = ctk.CTkFrame(
                scroll, fg_color=c["card_bg"], border_width=1, border_color=c["card_border"], corner_radius=12
            )
            card.pack(fill="x", pady=6)

            inner = ctk.CTkFrame(card, fg_color="transparent")
            inner.pack(fill="x", padx=20, pady=16)

            badge = ctk.CTkLabel(
                inner, text=u["username"][0].upper(), width=44, height=44,
                fg_color=self.accent, text_color="#FFFFFF", corner_radius=22,
                font=ctk.CTkFont(family="Segoe UI", size=17, weight="bold")
            )
            badge.pack(side="left", padx=(0, 14))

            info = ctk.CTkFrame(inner, fg_color="transparent")
            info.pack(side="left", fill="x", expand=True)

            ctk.CTkLabel(
                info, text=f"{u['username']}  (Verified Vault Owner)",
                font=ctk.CTkFont(family="Segoe UI", size=15, weight="bold"),
                text_color=c["text_primary"]
            ).pack(anchor="w")

            ctk.CTkLabel(
                info,
                text=f"Pose Samples: {u['samples']}/12   •   Ocular Signature: {u['ocular']}   •   Enrolled: {u['created']}",
                font=ctk.CTkFont(family=FluentTheme.FONT_FAMILY, size=12),
                text_color=c["text_secondary"]
            ).pack(anchor="w", pady=(3, 0))

            ctk.CTkButton(
                inner, text="Delete", width=86, height=32, corner_radius=6,
                fg_color="transparent", hover_color=c["card_hover"],
                border_width=1, border_color=c["danger"], text_color=c["danger"],
                font=ctk.CTkFont(family=FluentTheme.FONT_FAMILY, size=12, weight="bold"),
                command=lambda uname=u["username"]: self._delete_profile(uname)
            ).pack(side="right", padx=4)

            ctk.CTkButton(
                inner, text="Re-Enroll", width=98, height=32, corner_radius=6,
                fg_color=c["input_bg"], hover_color=c["card_hover"],
                border_width=1, border_color=c["card_border"], text_color=c["text_primary"],
                font=ctk.CTkFont(family=FluentTheme.FONT_FAMILY, size=12),
                command=lambda: self.switch_screen("enroll_demo")
            ).pack(side="right", padx=6)

    def _delete_profile(self, username: str):
        if not messagebox.askyesno("Delete Biometric Profile", f"Delete biometric profile '{username}'?"):
            return
        self.bio_engine.delete_profile(username)
        self.vault.state["users"] = [
            u for u in self.vault.state["users"]
            if u.get("username", u.get("name", "")).lower() != username.lower()
        ]
        self.vault.save_state()
        self.mock_users = self.vault.state["users"]
        if self.active_user and self.active_user.lower() == username.lower():
            self.active_user = None
            self.session_authenticated = False
        self.switch_screen("profiles", animate=False, force=True)

    # --------------------------------------------------------------------------
    # SCREEN 3: SETTINGS SCREEN (Theme, Custom Accent, System Tray & About)
    # --------------------------------------------------------------------------

    def _render_settings_screen(self):
        c = self.colors
        scroll = ctk.CTkScrollableFrame(self.viewport, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=34, pady=(20, 24))

        # --- Auto-Relock Lease Timer Setting Card ---
        timer_card = ctk.CTkFrame(
            scroll, fg_color=c["card_bg"], border_width=1, border_color=c["card_border"], corner_radius=12
        )
        timer_card.pack(fill="x", pady=6)
        t_inner = ctk.CTkFrame(timer_card, fg_color="transparent")
        t_inner.pack(fill="x", padx=20, pady=14)

        t_info = ctk.CTkFrame(t_inner, fg_color="transparent")
        t_info.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(
            t_info, text="Auto-Relock Lease Timer",
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            text_color=c["text_primary"]
        ).pack(anchor="w")
        ctk.CTkLabel(
            t_info,
            text="Duration all files for the active profile remain unlocked before NTFS lock automatically resurfaces",
            font=ctk.CTkFont(family=FluentTheme.FONT_FAMILY, size=12),
            text_color=c["text_secondary"]
        ).pack(anchor="w", pady=(2, 0))

        timer_options = ["1 Minute", "5 Minutes", "10 Minutes", "15 Minutes", "30 Minutes", "60 Minutes"]
        current_lbl = f"{self.auto_relock_minutes} Minute" if self.auto_relock_minutes == 1 else f"{self.auto_relock_minutes} Minutes"
        if current_lbl not in timer_options:
            current_lbl = "5 Minutes"

        def _on_timer_change(choice: str):
            mins = int(choice.split()[0])
            self.auto_relock_minutes = mins
            self.vault.state.setdefault("settings", {})["auto_relock_minutes"] = mins
            self.vault.save_state()
            if self.unlock_lease_remaining_sec > 0:
                self.unlock_lease_remaining_sec = mins * 60

        timer_menu = ctk.CTkOptionMenu(
            t_inner, values=timer_options, width=140, height=32,
            fg_color=c["input_bg"], button_color=self.accent,
            button_hover_color=self.accent_hover, text_color=c["text_primary"],
            font=ctk.CTkFont(family=FluentTheme.FONT_FAMILY, size=12, weight="bold"),
            command=_on_timer_change
        )
        timer_menu.set(current_lbl)
        timer_menu.pack(side="right")

        ctk.CTkLabel(
            scroll, text="Settings",
            font=ctk.CTkFont(family=FluentTheme.FONT_FAMILY, size=28, weight="bold"),
            text_color=c["text_primary"]
        ).pack(anchor="w")
        ctk.CTkLabel(
            scroll, text="Configure appearance, Windows 11 shell integration, system tray behavior & hardware defaults",
            font=ctk.CTkFont(family=FluentTheme.FONT_FAMILY, size=13),
            text_color=c["text_secondary"]
        ).pack(anchor="w", pady=(2, 18))

        # 1. APPEARANCE & THEME CARD
        ctk.CTkLabel(
            scroll, text="Appearance",
            font=ctk.CTkFont(family=FluentTheme.FONT_FAMILY, size=15, weight="bold"),
            text_color=c["text_primary"]
        ).pack(anchor="w", pady=(4, 8))

        theme_card = ctk.CTkFrame(
            scroll, fg_color=c["card_bg"], border_width=1, border_color=c["card_border"], corner_radius=12
        )
        theme_card.pack(fill="x", pady=(0, 14))

        r1 = ctk.CTkFrame(theme_card, fg_color="transparent")
        r1.pack(fill="x", padx=20, pady=14)
        ctk.CTkLabel(
            r1, text="App Theme Mode\nAutomatically adapt to Windows 11 Dark/Light setting or override manually",
            justify="left", font=ctk.CTkFont(family=FluentTheme.FONT_FAMILY, size=13),
            text_color=c["text_primary"]
        ).pack(side="left")

        theme_seg = ctk.CTkSegmentedButton(
            r1, values=["System", "Dark", "Light"],
            selected_color=self.accent, selected_hover_color=self.accent_hover,
            command=self._on_change_theme_mode
        )
        theme_seg.set(self.theme_preference)
        theme_seg.pack(side="right")

        # Collapsible Custom Accent Option hidden cleanly inside Appearance Card
        sep = ctk.CTkFrame(theme_card, fg_color=c["divider"], height=1)
        sep.pack(fill="x", padx=20)

        r2 = ctk.CTkFrame(theme_card, fg_color="transparent")
        r2.pack(fill="x", padx=20, pady=12)
        ctk.CTkLabel(
            r2, text="Custom Accent Colour (PowerToys / Fluent Highlights)",
            font=ctk.CTkFont(family=FluentTheme.FONT_FAMILY, size=13),
            text_color=c["text_secondary"]
        ).pack(side="left")

        accent_menu = ctk.CTkOptionMenu(
            r2, values=list(FluentTheme.ACCENTS.keys()),
            fg_color=self.accent, button_color=self.accent_hover,
            command=self._on_change_accent
        )
        accent_menu.set(self.accent_name)
        accent_menu.pack(side="right")

        # 2. SYSTEM TRAY & WINDOWS SHELL INTEGRATION
        ctk.CTkLabel(
            scroll, text="System & Window Behavior",
            font=ctk.CTkFont(family=FluentTheme.FONT_FAMILY, size=15, weight="bold"),
            text_color=c["text_primary"]
        ).pack(anchor="w", pady=(8, 8))

        sys_card = ctk.CTkFrame(
            scroll, fg_color=c["card_bg"], border_width=1, border_color=c["card_border"], corner_radius=12
        )
        sys_card.pack(fill="x", pady=(0, 14))

        self._add_setting_toggle_row(
            sys_card,
            "Minimize to System Tray on Close",
            "Keep BioVault running silently in the background when clicking the top-right '✕' button",
            self.minimize_to_tray_var
        )
        self._add_setting_toggle_row(
            sys_card,
            "Launch Automatically on Windows Startup",
            "Start BioVault minimized in the system tray when you sign into Windows",
            self.auto_start_var
        )
        self._add_setting_toggle_row(
            sys_card,
            "Windows Explorer Right-Click Context Menu",
            "Show 'Lock with BioVault' and 'Unlock with BioVault' on files and folders",
            self.ctx_menu_var
        )
        self._add_setting_toggle_row(
            sys_card,
            "Promote to Windows 11 First-Click Menu",
            "Display BioVault options immediately on right-click without clicking 'Show more options'",
            self.win11_direct_var,
            is_last=True
        )

        # 3. ABOUT & VERSION INFORMATION CARD
        ctk.CTkLabel(
            scroll, text="About & Version",
            font=ctk.CTkFont(family=FluentTheme.FONT_FAMILY, size=15, weight="bold"),
            text_color=c["text_primary"]
        ).pack(anchor="w", pady=(8, 8))

        about_card = ctk.CTkFrame(
            scroll, fg_color=c["card_bg"], border_width=1, border_color=c["card_border"], corner_radius=12
        )
        about_card.pack(fill="x", pady=(0, 10))

        ctk.CTkLabel(
            about_card,
            text=(
                "BioVault Desktop Utility   •   Version 1.0.0 (Build 2026.10 — x64)\n"
                "Biometric Engine:  InsightFace (buffalo_l 512-D) + MediaPipe 478-Point Mesh + 3-Region POS rPPG\n"
                "Install Location:  %LOCALAPPDATA%\\Programs\\BioVault   •   OS Lock: NTFS icacls (*S-1-1-0)"
            ),
            justify="left",
            font=ctk.CTkFont(family=FluentTheme.FONT_FAMILY, size=12),
            text_color=c["text_secondary"]
        ).pack(anchor="w", padx=20, pady=16)

    def _add_setting_toggle_row(self, parent, title: str, subtitle: str, var: ctk.BooleanVar, is_last=False):
        c = self.colors
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=20, pady=12)

        txt_col = ctk.CTkFrame(row, fg_color="transparent")
        txt_col.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(
            txt_col, text=title,
            font=ctk.CTkFont(family=FluentTheme.FONT_FAMILY, size=13, weight="bold"),
            text_color=c["text_primary"]
        ).pack(anchor="w")
        ctk.CTkLabel(
            txt_col, text=subtitle,
            font=ctk.CTkFont(family=FluentTheme.FONT_FAMILY, size=12),
            text_color=c["text_secondary"]
        ).pack(anchor="w")

        sw = ctk.CTkSwitch(
            row, text="", variable=var, progress_color=self.accent, width=46
        )
        sw.pack(side="right")

        if not is_last:
            sep = ctk.CTkFrame(parent, fg_color=c["divider"], height=1)
            sep.pack(fill="x", padx=20)
    
    
    def _apply_theme_tokens(self):
        mode = self._get_effective_mode()
        # Build native (LightHex, DarkHex) tuples so CustomTkinter switches all widgets in 1 native pass
        light_p = FluentTheme.PALETTES["Light"]
        dark_p = FluentTheme.PALETTES["Dark"]
        self.colors = {
            k: (light_p[k], dark_p[k]) for k in dark_p
        }
        self.accent, self.accent_hover = FluentTheme.ACCENTS[self.accent_name]
        ctk.set_appearance_mode(mode)

    def _on_change_theme_mode(self, new_mode: str):
        self.theme_preference = new_mode
        target_mode = self._get_effective_mode()
        # Native single-pass appearance switch — zero widget destruction, zero multi-step lag!
        ctk.set_appearance_mode(target_mode)

    def _on_change_accent(self, new_accent: str):
        old_acc = self.accent
        self.accent_name = new_accent
        self.accent, self.accent_hover = FluentTheme.ACCENTS[self.accent_name]

        # Only recolor the ~5 accent-coloured widgets in a single pass
        def _update_accent_only(widget):
            for child in widget.winfo_children():
                for prop in ("fg_color", "border_color", "text_color", "progress_color", "selected_color"):
                    try:
                        if str(child.cget(prop)).lower() == old_acc.lower():
                            child.configure(**{prop: self.accent})
                    except Exception:
                        pass
                _update_accent_only(child)

        _update_accent_only(self)

    def _animate_theme_transition(
        self, old_c: dict, new_c: dict, old_acc: str, new_acc: str, step: int = 1, steps: int = 8
    ):
        """Smoothly cross-fades all widget colours in place without rebuilding or refreshing the screen."""
        t = step / float(steps)
        eased_t = 1.0 - ((1.0 - t) ** 2)

        # Build reverse colour map from old palette -> interpolated hex colour
        color_map = {}
        for k, old_hex in old_c.items():
            target_hex = new_c.get(k, old_hex)
            color_map[old_hex.lower()] = _lerp_hex(old_hex, target_hex, eased_t)
        color_map[old_acc.lower()] = _lerp_hex(old_acc, new_acc, eased_t)

        def _extract_current_hex(val):
            if isinstance(val, (tuple, list)):
                mode_idx = 0 if self._get_effective_mode() == "Light" else 1
                val = val[min(mode_idx, len(val) - 1)]
            return str(val).lower() if val else ""

        def _walk_and_recolor(widget):
            for child in widget.winfo_children():
                for prop in ("fg_color", "border_color", "text_color", "progress_color", " selected_color"):
                    prop = prop.strip()
                    try:
                        cur_val = _extract_current_hex(child.cget(prop))
                        if cur_val in color_map:
                            child.configure(**{prop: color_map[cur_val]})
                    except Exception:
                        pass
                _walk_and_recolor(child)

        # Update root shell and walk all existing children in place
        self.configure(fg_color=_lerp_hex(old_c["canvas_bg"], new_c["canvas_bg"], eased_t))
        _walk_and_recolor(self)

        # On final step, snap exact target tokens so subsequent transitions have exact keys
        if step < steps:
            self.after(
                16,
                lambda: self._animate_theme_transition(color_map_to_palette(old_c, new_c, eased_t), new_c, _lerp_hex(old_acc, new_acc, eased_t), new_acc, step + 1, steps)
            )
        else:
            self._refresh_hw_card()

    # --------------------------------------------------------------------------
    # SHARED EMBEDDED CAMERA ENGINE (For Registration & Verification Previews)
    # --------------------------------------------------------------------------

    def _start_embedded_camera(self, target_label: ctk.CTkLabel, host_frame: ctk.CTkFrame, mode: str = "verify"):
        self._stop_active_camera()
        self._cam_session_id = getattr(self, "_cam_session_id", 0) + 1
        session_id = self._cam_session_id
        self._cam_running = True
        self._cam_target_lbl = target_label
        self._cam_size = (640, 380)
        self._manual_sim_override = False
        self._last_face_bbox = None
        self._last_eye_rois = []
        self._last_pupil_pts = []
        self._smoothed_bbox = None
        self._latest_pil_frame = None
        self._latest_telemetry = None
        self._last_ver_ui_state = None
        self._last_reg_ui_state = None
        self.bio_engine.reset_session()

        def _measure_host(event=None):
            if not host_frame.winfo_exists():
                return
            try:
                scale = host_frame._get_widget_scaling()
            except Exception:
                scale = 1.0
            lw = int((host_frame.winfo_width() - 12) / max(1.0, scale))
            lh = int((host_frame.winfo_height() - 12) / max(1.0, scale))
            if lw > 160 and lh > 120:
                self._cam_size = (min(lw, 640), min(lh, 380))

        host_frame.bind("<Configure>", _measure_host)
        self.after(60, _measure_host)

        dev_idx = getattr(self.hw, "selected_index", getattr(self.hw, "active_index", 0))
        self._active_cam_thread = threading.Thread(
            target=self._camera_worker,
            args=(dev_idx, session_id, mode),
            daemon=True
        )
        self._active_cam_thread.start()
        self._poll_camera_ui(session_id, mode)

    def _poll_camera_ui(self, session_id: int, mode: str):
        if not getattr(self, "_cam_running", False) or getattr(self, "_cam_session_id", 0) != session_id:
            return

        pil_img = getattr(self, "_latest_pil_frame", None)
        if pil_img is not None:
            self._latest_pil_frame = None
            self._safe_paint_cam_frame(pil_img, self._cam_size, session_id)

        telem = getattr(self, "_latest_telemetry", None)
        if telem is not None:
            self._latest_telemetry = None
            if mode == "register":
                self._on_live_reg_telemetry(telem, session_id)
            elif mode == "verify":
                self._on_live_ver_telemetry(telem, session_id)

        self.after(28, lambda: self._poll_camera_ui(session_id, mode))

    def _resize_crop(self, frame: np.ndarray, target_w: int, target_h: int) -> np.ndarray:
        h, w = frame.shape[:2]
        if w <= 0 or h <= 0:
            return np.zeros((target_h, target_w, 3), dtype=np.uint8)
        scale = max(target_w / float(w), target_h / float(h))
        nw, nh = int(w * scale), int(h * scale)
        resized = cv2.resize(frame, (nw, nh), interpolation=cv2.INTER_LINEAR)
        x0 = max(0, (nw - target_w) // 2)
        y0 = max(0, (nh - target_h) // 2)
        return resized[y0:y0 + target_h, x0:x0 + target_w]

    def _camera_worker(self, device_index: int, session_id: int, mode: str):
        cap = None
        if device_index >= 0:
            for backend in (cv2.CAP_DSHOW, cv2.CAP_MSMF, cv2.CAP_ANY):
                try:
                    c_try = cv2.VideoCapture(device_index, backend)
                    if c_try is not None and c_try.isOpened():
                        c_try.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                        ret, test_f = c_try.read()
                        if ret and test_f is not None and test_f.size > 0:
                            cap = c_try
                            break
                        c_try.release()
                except Exception:
                    pass

        color_map = {
            "guide": (56, 189, 248),   # Cyan-Blue
            "ok":    (16, 185, 129),   # Emerald Green
            "warn":  (245, 158, 11),   # Amber Warning
            "error": (239, 68, 68),    # Red Error
        }

        try:
            while self._cam_running and self._cam_session_id == session_id:
                target_w, target_h = getattr(self, "_cam_size", (640, 380))
                raw_frame = None

                if cap is not None and cap.isOpened() and not getattr(self, "_manual_sim_override", False):
                    ret, frm = cap.read()
                    if ret and frm is not None and frm.size > 0:
                        raw_frame = cv2.flip(frm, 1)

                if raw_frame is not None:
                    frame_bgr = self._resize_crop(raw_frame, target_w, target_h)
                    try:
                        if mode == "register":
                            res = self.bio_engine.process_enrollment_frame(frame_bgr)
                        else:
                            if getattr(self, "_verify_mode_purpose", "ITEM_UNLOCK") == "APP_STARTUP":
                                owner = None
                            else:
                                owner = self._current_unlock_target.get("owner") if self._current_unlock_target else self.active_user
                            res = self.bio_engine.process_verification_frame(frame_bgr, expected_owner=owner)

                        self._last_face_bbox = res.get("bbox")
                        self._last_eye_rois = res.get("eye_rois", [])
                        self._last_pupil_pts = res.get("pupil_pts", [])
                        self._cam_oval_color = color_map.get(res.get("oval_state", "guide"), (56, 189, 248))
                        self._latest_telemetry = res
                    except Exception:
                        import traceback
                        traceback.print_exc()
                        self._last_face_bbox = None
                        self._last_eye_rois = []
                        self._last_pupil_pts = []

                    display_bgr = self._draw_square_face_frame(frame_bgr, target_w, target_h)
                else:
                    display_bgr = np.full((target_h, target_w, 3), (22, 25, 34), dtype=np.uint8)
                    self._last_face_bbox = None
                    self._last_eye_rois = []
                    self._last_pupil_pts = []

                rgb = cv2.cvtColor(display_bgr, cv2.COLOR_BGR2RGB)
                self._latest_pil_frame = Image.fromarray(rgb)
                time.sleep(0.018)
        finally:
            if cap is not None:
                try:
                    cap.release()
                except Exception:
                    pass

    def _draw_square_face_frame(self, frame_bgr: np.ndarray, w: int, h: int) -> np.ndarray:
        """Draws ONLY the moving face square + eye boxes & iris dots during the blink phase (no stats/text)."""
        out = frame_bgr.copy()
        bbox = getattr(self, "_last_face_bbox", None)

        if bbox is None:
            self._smoothed_bbox = None
            return out

        color_rgb = getattr(self, "_cam_oval_color", (56, 189, 248))
        color_bgr = (color_rgb[2], color_rgb[1], color_rgb[0])

        fx, fy, fw, fh = bbox
        side = int(max(fw, fh) * 1.10)
        cx, cy = fx + fw // 2, fy + fh // 2

        tx1 = float(max(8, cx - side // 2))
        ty1 = float(max(8, cy - side // 2))
        tx2 = float(min(w - 8, tx1 + side))
        ty2 = float(min(h - 8, ty1 + side))

        prev = getattr(self, "_smoothed_bbox", None)
        alpha = 0.50
        if prev is None:
            curr = [tx1, ty1, tx2, ty2]
        else:
            curr = [
                prev[0] + alpha * (tx1 - prev[0]),
                prev[1] + alpha * (ty1 - prev[1]),
                prev[2] + alpha * (tx2 - prev[2]),
                prev[3] + alpha * (ty2 - prev[3]),
            ]
        self._smoothed_bbox = curr
        x1, y1, x2, y2 = [int(v) for v in curr]

        cv2.rectangle(out, (x1, y1), (x2, y2), color_bgr, 2, cv2.LINE_AA)

        corner_len = max(16, (x2 - x1) // 6)
        thick = 4
        cv2.line(out, (x1, y1), (x1 + corner_len, y1), color_bgr, thick, cv2.LINE_AA)
        cv2.line(out, (x1, y1), (x1, y1 + corner_len), color_bgr, thick, cv2.LINE_AA)
        cv2.line(out, (x2, y1), (x2 - corner_len, y1), color_bgr, thick, cv2.LINE_AA)
        cv2.line(out, (x2, y1), (x2, y1 + corner_len), color_bgr, thick, cv2.LINE_AA)
        cv2.line(out, (x1, y2), (x1 + corner_len, y2), color_bgr, thick, cv2.LINE_AA)
        cv2.line(out, (x1, y2), (x1, y2 - corner_len), color_bgr, thick, cv2.LINE_AA)
        cv2.line(out, (x2, y2), (x2 - corner_len, y2), color_bgr, thick, cv2.LINE_AA)
        cv2.line(out, (x2, y2), (x2, y2 - corner_len), color_bgr, thick, cv2.LINE_AA)

        # Draw eye frames and yellow iris center dots during the blink phase
        for (ex1, ey1, ex2, ey2) in getattr(self, "_last_eye_rois", []):
            cv2.rectangle(out, (ex1, ey1), (ex2, ey2), (180, 180, 180), 1, cv2.LINE_AA)
        for (px, py) in getattr(self, "_last_pupil_pts", []):
            cv2.circle(out, (px, py), 3, (0, 255, 255), -1, cv2.LINE_AA)

        return out

    def _safe_paint_cam_frame(self, pil_img, size, session_id: int):
        if not getattr(self, "_cam_running", False) or getattr(self, "_cam_session_id", 0) != session_id:
            return
        lbl = getattr(self, "_cam_target_lbl", None)
        if lbl is None:
            return
        try:
            if not lbl.winfo_exists():
                return
            ctk_img = ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=size)
            lbl.configure(image=ctk_img, text="")
            lbl._image_ref = ctk_img
        except tk.TclError:
            pass

    def _stop_active_camera(self):
        self._cam_running = False
        self._cam_session_id = getattr(self, "_cam_session_id", 0) + 1

    def _on_live_reg_telemetry(self, res: dict, session_id: int):
        """Updates Registration UI widgets ONLY when values change to eliminate Tkinter redraw lag."""
        if not getattr(self, "_cam_running", False) or getattr(self, "_cam_session_id", 0) != session_id:
            return
        if self.active_nav != "enroll_demo" or not hasattr(self, "reg_inst_lbl") or not self.reg_inst_lbl.winfo_exists():
            return

        c = self.colors
        gates = tuple(res["gates"])
        inst_txt = res["instruction"]
        stepper_txt = res.get("stepper", "")
        samples = int(res["samples"])
        blinks = int(res["blinks"])

        prev = getattr(self, "_last_reg_ui_state", None)
        curr = (gates, inst_txt, stepper_txt, samples, blinks)

        if prev != curr:
            self._last_reg_ui_state = curr
            if prev is None or prev[0] != gates:
                g_dist, g_light, g_glare, g_eyes = gates
                self._set_gate_pill(self.gate_dist,  g_dist,  "Distance Optimal" if g_dist else "Adjust Face Distance")
                self._set_gate_pill(self.gate_light, g_light, "Lighting & Sharpness" if g_light else "Improve Lighting")
                self._set_gate_pill(self.gate_glare, g_glare, "Eye Socket Clear" if g_glare else "Obstruction Detected")
                self._set_gate_pill(self.gate_eyes,  g_eyes,  "Eyes Wide Open" if g_eyes else "Open Both Eyes")

            if prev is None or prev[1] != inst_txt or prev[0] != gates:
                self.reg_inst_lbl.configure(
                    text=inst_txt,
                    text_color=c["text_primary"] if all(gates) else c["warning"]
                )
            if stepper_txt and (prev is None or prev[2] != stepper_txt):
                self.reg_stepper_lbl.configure(text=stepper_txt)

            if prev is None or prev[3] != samples or prev[4] != blinks:
                total_done = samples + blinks
                self.reg_pose_lbl.configure(text=f"Pose Snapshots:    {samples} / 12")
                self.reg_prog_bar.set(total_done / 14.0)
                self.reg_prog_txt.configure(text=f"Overall Progress:  {total_done} / 14 Steps")
                self.reg_dot1.configure(image=self._dot_on if blinks >= 1 else self._dot_off)
                self.reg_dot2.configure(image=self._dot_on if blinks >= 2 else self._dot_off)

        if res["completed"]:
            self._stop_active_camera()
            raw_name = (
                self.reg_username_entry.get().strip()
                if hasattr(self, "reg_username_entry") and self.reg_username_entry.winfo_exists()
                else ""
            )
            uname = raw_name or os.environ.get("USERNAME", "Owner")

            profile_meta = self.bio_engine.save_enrolled_profile(uname)
            self.vault.state["users"] = [
                u for u in self.vault.state["users"]
                if u.get("username", u.get("name", "")).lower() != profile_meta["username"].lower()
            ]
            self.vault.state["users"].append(profile_meta)
            self.vault.save_state()
            self.mock_users = self.vault.state["users"]

            self.active_user = profile_meta["username"]
            self.session_authenticated = True

            messagebox.showinfo(
                "BioVault",
                f"Biometric profile for '{profile_meta['username']}' enrolled and saved to:\n"
                f"{os.path.join(self.bio_engine.profiles_dir, profile_meta['username'] + '.npz')}"
            )
            self.switch_screen("dashboard", animate=True, force=True)

    def _on_live_ver_telemetry(self, res: dict, session_id: int):
        """Updates Verification UI widgets ONLY when values change to eliminate Tkinter redraw lag."""
        if not getattr(self, "_cam_running", False) or getattr(self, "_cam_session_id", 0) != session_id:
            return
        if self.active_nav != "verify_demo" or not hasattr(self, "ver_status_lbl") or not self.ver_status_lbl.winfo_exists():
            return

        c = self.colors
        self._ver_timer_paused = res["pause_timer"]

        prog = float(res["progress"])
        pct = int(round(prog * 100))
        blinks = int(res["blinks"])
        status_txt = res["status_text"]
        status_role = res["status_role"]

        prev = getattr(self, "_last_ver_ui_state", None)
        curr = (pct, blinks, status_txt, status_role)

        if prev != curr:
            self._last_ver_ui_state = curr
            role_map = {
                "primary": c["text_primary"],
                "secondary": c["text_secondary"],
                "warning": c["warning"],
                "danger": c["danger"]
            }
            if prev is None or prev[2] != status_txt or prev[3] != status_role:
                self.ver_status_lbl.configure(
                    text=status_txt,
                    text_color=role_map.get(status_role, c["text_primary"])
                )
            if prev is None or prev[0] != pct:
                self.ver_prog_bar.set(prog)
                self.ver_pct_lbl.configure(text=f"{pct}%")
            if prev is None or prev[1] != blinks:
                self.ver_dot1_lbl.configure(
                    image=self._dot_on if blinks >= 1 else self._dot_off,
                    text_color=c["success"] if blinks >= 1 else c["text_secondary"]
                )
                self.ver_dot2_lbl.configure(
                    image=self._dot_on if blinks >= 2 else self._dot_off,
                    text_color=c["success"] if blinks >= 2 else c["text_secondary"]
                )

        if res["unlocked"]:
            self._stop_active_camera()
            self.active_user = res.get("matched_user") or self.active_user or (
                self.mock_users[0].get("username", self.mock_users[0].get("name", "Owner"))
                if self.mock_users else "Owner"
            )
            self.session_authenticated = True
            if getattr(self, "_verify_mode_purpose", "ITEM_UNLOCK") == "ITEM_UNLOCK":
                target_item = getattr(self, "_current_unlock_target", None)
                self._verify_mode_purpose = "ITEM_UNLOCK"
                self._trigger_user_batch_unlock(target_item)
                return
            self._verify_mode_purpose = "ITEM_UNLOCK"
            self.switch_screen("dashboard", animate=True, force=True)


    # --------------------------------------------------------------------------
    # SCREEN 4: BIOMETRIC REGISTRATION STUDIO
    # - No Timers anywhere
    # - No FPS Counter in header
    # - [ ✔ ] and [ ✖ ] Live Quality Gates
    # - Coloured Dots (⚪ -> 🟢) for Blink Liveness
    # - Interactive Simulator Bar to test all live warning states
    # --------------------------------------------------------------------------

    def _render_registration_screen(self):
        c = self.colors
        self._reg_samples = 0
        self._reg_blinks = 0
        self._cam_oval_color = (52, 211, 153)

        container = ctk.CTkFrame(self.viewport, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=16, pady=(8, 12))

        # 1. Header Bar with Profile Name Input
        hdr = ctk.CTkFrame(
            container, fg_color=c["card_bg"], border_width=1, border_color=c["card_border"],
            height=42, corner_radius=10
        )
        hdr.pack(fill="x", pady=(0, 6))
        hdr.pack_propagate(False)

        ctk.CTkButton(
            hdr, text="← Cancel", width=88, height=28, corner_radius=6,
            fg_color=c["input_bg"], hover_color=c["card_hover"], text_color=c["text_primary"],
            font=ctk.CTkFont(family=FluentTheme.FONT_FAMILY, size=12, weight="bold"),
            command=lambda: self.switch_screen("profiles")
        ).pack(side="left", padx=10)

        ctk.CTkLabel(
            hdr, text="ENROLL NEW BIOMETRIC PROFILE",
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            text_color=c["text_primary"]
        ).pack(side="left", expand=True)

        name_box = ctk.CTkFrame(hdr, fg_color="transparent")
        name_box.pack(side="right", padx=12)
        ctk.CTkLabel(
            name_box, text="Profile Name:",
            font=ctk.CTkFont(family=FluentTheme.FONT_FAMILY, size=12),
            text_color=c["text_secondary"]
        ).pack(side="left", padx=(0, 6))

        default_new_name = (
            self.active_user
            if self.active_user else
            (f"User_{len(self.mock_users) + 1}" if self.mock_users else os.environ.get("USERNAME", "Owner"))
        )
        self.reg_username_entry = ctk.CTkEntry(
            name_box, width=140, height=28,
            font=ctk.CTkFont(family=FluentTheme.FONT_FAMILY, size=12, weight="bold")
        )
        self.reg_username_entry.insert(0, default_new_name)
        self.reg_username_entry.pack(side="left")

        # 2. Stepper Bar
        stepper = ctk.CTkFrame(
            container, fg_color=c["card_bg"], border_width=1, border_color=c["card_border"],
            height=32, corner_radius=8
        )
        stepper.pack(fill="x", pady=(0, 8))
        stepper.pack_propagate(False)

        self.reg_stepper_lbl = ctk.CTkLabel(
            stepper,
            text="[1. Warm-Up ✔]   ━━━   [2. Center ●]   ━━━   [3. Left ○]   ━━━   [4. Right ○]   ━━━   [5. Seal ○]",
            font=ctk.CTkFont(family=FluentTheme.FONT_FAMILY, size=12, weight="bold"),
            text_color=self.accent
        )
        self.reg_stepper_lbl.pack(expand=True)

        # 3. Main Split Body
        body = ctk.CTkFrame(container, fg_color="transparent")
        body.pack(fill="both", expand=True)

        right_col = ctk.CTkFrame(
            body, fg_color=c["card_bg"], border_width=1, border_color=c["card_border"],
            width=285, corner_radius=12
        )
        right_col.pack(side="right", fill="y", padx=(8, 0))
        right_col.pack_propagate(False)

        left_col = ctk.CTkFrame(
            body, fg_color=c["card_bg"], border_width=1, border_color=c["card_border"], corner_radius=12
        )
        left_col.pack(side="left", fill="both", expand=True)

        prog_row = ctk.CTkFrame(left_col, fg_color="transparent")
        prog_row.pack(side="bottom", fill="x", padx=12, pady=(4, 10))

        self.reg_prog_bar = ctk.CTkProgressBar(prog_row, height=12, progress_color=self.accent)
        self.reg_prog_bar.pack(fill="x", pady=(0, 4))
        self.reg_prog_bar.set(0.0)

        self.reg_prog_txt = ctk.CTkLabel(
            prog_row, text="Overall Progress:  0 / 14 Steps",
            font=ctk.CTkFont(family=FluentTheme.FONT_FAMILY, size=12, weight="bold"),
            text_color=c["text_secondary"]
        )
        self.reg_prog_txt.pack()

        cam_host = ctk.CTkFrame(left_col, fg_color=c["input_bg"], corner_radius=8)
        cam_host.pack(side="top", fill="both", expand=True, padx=8, pady=(8, 4))
        cam_host.pack_propagate(False)

        self.reg_cam_lbl = ctk.CTkLabel(cam_host, text="Starting Camera Sensor...", fg_color="transparent")
        self.reg_cam_lbl.pack(fill="both", expand=True)

        ctk.CTkLabel(
            right_col, text="CURRENT INSTRUCTION",
            font=ctk.CTkFont(family=FluentTheme.FONT_FAMILY, size=11, weight="bold"),
            text_color=c["text_muted"]
        ).pack(anchor="w", padx=14, pady=(12, 4))

        self.reg_inst_card = ctk.CTkFrame(
            right_col, fg_color=c["input_bg"], border_width=1, border_color=c["card_border"], corner_radius=8
        )
        self.reg_inst_card.pack(fill="x", padx=12, pady=(0, 10))

        self.reg_inst_lbl = ctk.CTkLabel(
            self.reg_inst_card,
            text="Step 2/5 (Center Pose):\nLook straight at the camera and hold steady.",
            justify="left", wraplength=235,
            font=ctk.CTkFont(family=FluentTheme.FONT_FAMILY, size=13, weight="bold"),
            text_color=c["text_primary"]
        )
        self.reg_inst_lbl.pack(anchor="w", padx=12, pady=10)

        ctk.CTkLabel(
            right_col, text="LIVE QUALITY GATES",
            font=ctk.CTkFont(family=FluentTheme.FONT_FAMILY, size=11, weight="bold"),
            text_color=c["text_muted"]
        ).pack(anchor="w", padx=14, pady=(2, 4))

        self.gate_dist = self._create_gate_pill(right_col, True, "Distance Optimal")
        self.gate_light = self._create_gate_pill(right_col, True, "Lighting & Sharpness")
        self.gate_glare = self._create_gate_pill(right_col, True, "Eye Socket Clear")
        self.gate_eyes = self._create_gate_pill(right_col, True, "Eyes Wide Open")

        summary_box = ctk.CTkFrame(right_col, fg_color=c["input_bg"], corner_radius=8)
        summary_box.pack(side="bottom", fill="x", padx=12, pady=12)

        self.reg_pose_lbl = ctk.CTkLabel(
            summary_box, text="Pose Snapshots:    0 / 12",
            font=ctk.CTkFont(family=FluentTheme.FONT_FAMILY, size=12, weight="bold"),
            text_color=c["text_primary"]
        )
        self.reg_pose_lbl.pack(anchor="w", padx=12, pady=(8, 4))

        blink_row = ctk.CTkFrame(summary_box, fg_color="transparent")
        blink_row.pack(fill="x", padx=12, pady=(2, 8))
        ctk.CTkLabel(
            blink_row, text="Blink Liveness:",
            font=ctk.CTkFont(family=FluentTheme.FONT_FAMILY, size=12, weight="bold"),
            text_color=c["text_primary"]
        ).pack(side="left", padx=(0, 10))

        self._dot_off = create_blink_dot_icon(False)
        self._dot_on = create_blink_dot_icon(True)

        self.reg_dot1 = ctk.CTkLabel(
            blink_row, text=" Blink 1", image=self._dot_off, compound="left",
            font=ctk.CTkFont(family=FluentTheme.FONT_FAMILY, size=12)
        )
        self.reg_dot1.pack(side="left", padx=(0, 10))
        self.reg_dot2 = ctk.CTkLabel(
            blink_row, text=" Blink 2", image=self._dot_off, compound="left",
            font=ctk.CTkFont(family=FluentTheme.FONT_FAMILY, size=12)
        )
        self.reg_dot2.pack(side="left")

        self._start_embedded_camera(self.reg_cam_lbl, cam_host, mode="register")

    def _create_gate_pill(self, parent, passed: bool, label_text: str) -> ctk.CTkLabel:
        c = self.colors
        row = ctk.CTkFrame(parent, fg_color=c["input_bg"], height=34, corner_radius=6)
        row.pack(fill="x", padx=14, pady=3)
        row.pack_propagate(False)

        prefix = "[ ✔ ]" if passed else "[ ✖ ]"
        col = c["success"] if passed else c["danger"]
        lbl = ctk.CTkLabel(
            row, text=f"{prefix}  {label_text}",
            font=ctk.CTkFont(family=FluentTheme.FONT_FAMILY, size=12, weight="bold"),
            text_color=col
        )
        lbl.pack(side="left", padx=10)
        return lbl

    def _set_gate_pill(self, lbl: ctk.CTkLabel, passed: bool, text: str):
        c = self.colors
        prefix = "[ ✔ ]" if passed else "[ ✖ ]"
        lbl.configure(text=f"{prefix}  {text}", text_color=c["success"] if passed else c["danger"])

    def _apply_reg_sim_state(self, state_code: str):
        self._manual_sim_override = True
        c = self.colors
        # Reset all 4 gates to [ ✔ ] first
        self._set_gate_pill(self.gate_dist, True, "Distance Optimal")
        self._set_gate_pill(self.gate_light, True, "Lighting & Sharpness")
        self._set_gate_pill(self.gate_glare, True, "Eye Socket Clear")
        self._set_gate_pill(self.gate_eyes, True, "Eyes Wide Open")
        self.reg_inst_card.configure(border_color=c["card_border"])
        self._cam_oval_color = (52, 211, 153)

        if state_code == "NORMAL":
            self.reg_inst_lbl.configure(
                text="Step 2/5:\nTurn your head slightly LEFT <- and keep both eyes open.",
                text_color=c["text_primary"]
            )
            self.reg_pose_lbl.configure(text="Pose Snapshots:    6 / 12")
            # UPDATED: Use the new coloured dot icon labels
            self.reg_dot1.configure(image=self._dot_off, text_color=c["text_secondary"])
            self.reg_dot2.configure(image=self._dot_off, text_color=c["text_secondary"])
            self.reg_prog_bar.set(6 / 14.0)
            self.reg_prog_txt.configure(text="Overall Progress:  6 / 14 Steps")

        elif state_code == "LOW_LIGHT":
            self._set_gate_pill(self.gate_light, False, "Improve Room Lighting")
            self.reg_inst_card.configure(border_color=c["warning"])
            self.reg_inst_lbl.configure(
                text="⚠ ACTION PAUSED:\nLow light detected (camera shutter slowed). Please improve lighting condition.",
                text_color=c["warning"]
            )
            self._cam_oval_color = (251, 191, 36)

        elif state_code == "BACKLIGHT":
            self._set_gate_pill(self.gate_light, False, "Strong Backlight Detected")
            self.reg_inst_card.configure(border_color=c["warning"])
            self.reg_inst_lbl.configure(
                text="⚠ ACTION PAUSED:\nStrong backlight behind you. Face the light source, not away from it.",
                text_color=c["warning"]
            )
            self._cam_oval_color = (251, 191, 36)

        elif state_code == "EYES_SHUT":
            self._set_gate_pill(self.gate_eyes, False, "Open Eyes Wide")
            self.reg_inst_card.configure(border_color=c["danger"])
            self.reg_inst_lbl.configure(
                text="⚠ ACTION PAUSED:\nEyes closed detected. Please keep both eyes wide open during pose capture.",
                text_color=c["danger"]
            )
            self._cam_oval_color = (248, 113, 113)

        elif state_code == "GLARE":
            self._set_gate_pill(self.gate_glare, False, "Eye Socket Obscured")
            self.reg_inst_card.configure(border_color=c["warning"])
            self.reg_inst_lbl.configure(
                text="⚠ ACTION PAUSED:\nEyes are not visible. Remove dark glasses or tilt head to avoid lens glare.",
                text_color=c["warning"]
            )
            self._cam_oval_color = (251, 191, 36)

        elif state_code == "MULTI_FACE":
            self._set_gate_pill(self.gate_dist, False, "Multiple Faces in Frame")
            self._set_gate_pill(self.gate_light, False, "Security Pause")
            self._set_gate_pill(self.gate_glare, False, "Security Pause")
            self._set_gate_pill(self.gate_eyes, False, "Security Pause")
            self.reg_inst_card.configure(border_color=c["danger"])
            self.reg_inst_lbl.configure(
                text="🚨 SECURITY PAUSE:\nMultiple faces detected in frame! Ensure only you are in view.",
                text_color=c["danger"]
            )
            self._cam_oval_color = (248, 113, 113)

        elif state_code == "BLINK_SEAL":
            self.reg_stepper_lbl.configure(
                text="[1. Warm-Up ✔]   ━━━   [2. Center ✔]   ━━━   [3. Left ✔]   ━━━   [4. Right ✔]   ━━━   [5. Seal ●]"
            )
            self.reg_inst_lbl.configure(
                text="Step 5/5 (Final Seal):\nBlink naturally twice to seal your biometric profile.",
                text_color=c["success"]
            )
            self.reg_pose_lbl.configure(text="Pose Snapshots:    12 / 12  [ ✔ ]")
            # UPDATED: Light up Blink 1 in Emerald Green and keep Blink 2 pending
            self.reg_dot1.configure(image=self._dot_on, text_color=c["success"])
            self.reg_dot2.configure(image=self._dot_off, text_color=c["text_secondary"])
            self.reg_prog_bar.set(13 / 14.0)
            self.reg_prog_txt.configure(text="Overall Progress:  13 / 14 Steps")

    # --------------------------------------------------------------------------
    # SCREEN 5: BIOMETRIC VERIFICATION GATE (ZERO-TRUST UNLOCK)
    # - Clean Top Bar (No Shield Icon) + Integer-Only Countdown Timer (10s..0s)
    # - 1 Unified Biometric Verification Progress Bar
    # - Coloured Dots (⚪ -> 🟢) for Blink Liveness Check
    # - Clean Keyboard-Only Icon Button for Recovery Password Fallback
    # - 4 Terminal Diagnostic Error Cards when verification fails
    # --------------------------------------------------------------------------

    def _render_verification_screen(self):
        c = self.colors
        self._ver_seconds = 30
        self._ver_timer_paused = False
        self._cam_oval_color = (56, 189, 248)

        if getattr(self, "_verify_mode_purpose", "ITEM_UNLOCK") == "APP_STARTUP":
            target_name = "BioVault Profile Session Login"
            target_owner = "Any Registered Profile"
        else:
            default_owner = self.active_user or (self.mock_users[0]["username"] if self.mock_users else "Owner")
            target = getattr(self, "_current_unlock_target", None) or {
                "name": "Vault Access",
                "owner": default_owner
            }
            target_name = target["name"]
            target_owner = target["owner"]

        container = ctk.CTkFrame(self.viewport, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=16, pady=(8, 12))

        # 1. Top Gate Header
        hdr = ctk.CTkFrame(
            container, fg_color=c["card_bg"], border_width=1, border_color=c["card_border"],
            height=54, corner_radius=10
        )
        hdr.pack(fill="x", pady=(0, 8))
        hdr.pack_propagate(False)

        left_hdr = ctk.CTkFrame(hdr, fg_color="transparent")
        left_hdr.pack(side="left", padx=18, pady=6)

        ctk.CTkLabel(
            left_hdr, text="BIOVAULT ZERO-TRUST GATE",
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            text_color=c["text_primary"]
        ).pack(anchor="w")

        ctk.CTkLabel(
            left_hdr, text=f'Unlocking: "{target_name}"   •   Owner: {target_owner}',
            font=ctk.CTkFont(family=FluentTheme.FONT_FAMILY, size=12),
            text_color=c["text_secondary"]
        ).pack(anchor="w")

        self.ver_timer_lbl = ctk.CTkLabel(
            hdr, text="Time: 30s",
            font=ctk.CTkFont(family="Segoe UI", size=15, weight="bold"),
            text_color=self.accent
        )
        self.ver_timer_lbl.pack(side="right", padx=18)

        # 2. Persistent Bottom Emergency Recovery Password Bar
        pwd_bar = ctk.CTkFrame(container, fg_color="transparent")
        pwd_bar.pack(side="bottom", fill="x", pady=(8, 0))

        kb_icon = create_keyboard_only_icon(size=(22, 15))
        pwd_btn = ctk.CTkButton(
            pwd_bar,
            text="  Use Emergency Recovery Password",
            image=kb_icon, compound="left",
            height=38, corner_radius=8,
            fg_color=c["card_bg"], hover_color=c["card_hover"],
            border_width=1, border_color=c["card_border"], text_color=c["text_primary"],
            font=ctk.CTkFont(family=FluentTheme.FONT_FAMILY, size=13, weight="bold"),
            command=self._open_mock_password_dialog
        )
        pwd_btn.image = kb_icon
        pwd_btn.pack(fill="x")

        # 3. Dynamic Center Stage
        self.ver_stage_card = ctk.CTkFrame(
            container, fg_color=c["card_bg"], border_width=1, border_color=c["card_border"], corner_radius=12
        )
        self.ver_stage_card.pack(side="top", fill="both", expand=True)

        self._build_live_verification_stage()
        self.after(1000, self._tick_verification_integer_timer)

    def _build_live_verification_stage(self):
        for w in self.ver_stage_card.winfo_children():
            w.destroy()

        c = self.colors
        self._dot_off = create_blink_dot_icon(False)
        self._dot_on = create_blink_dot_icon(True)

        metrics = ctk.CTkFrame(self.ver_stage_card, fg_color=c["input_bg"], corner_radius=10)
        metrics.pack(side="bottom", fill="x", padx=10, pady=(0, 8))

        r1 = ctk.CTkFrame(metrics, fg_color="transparent")
        r1.pack(fill="x", padx=16, pady=(8, 4))

        ctk.CTkLabel(
            r1, text="Biometric Verification", width=165, anchor="w",
            font=ctk.CTkFont(family=FluentTheme.FONT_FAMILY, size=13, weight="bold"),
            text_color=c["text_primary"]
        ).pack(side="left")

        self.ver_prog_bar = ctk.CTkProgressBar(r1, height=13, progress_color=self.accent)
        self.ver_prog_bar.pack(side="left", fill="x", expand=True, padx=12)
        self.ver_prog_bar.set(0.0)

        self.ver_pct_lbl = ctk.CTkLabel(
            r1, text="0%", width=45, anchor="e",
            font=ctk.CTkFont(family=FluentTheme.FONT_FAMILY, size=13, weight="bold"),
            text_color=self.accent
        )
        self.ver_pct_lbl.pack(side="right")

        r2 = ctk.CTkFrame(metrics, fg_color="transparent")
        r2.pack(fill="x", padx=16, pady=(2, 8))

        ctk.CTkLabel(
            r2, text="Blink Liveness Check", width=165, anchor="w",
            font=ctk.CTkFont(family=FluentTheme.FONT_FAMILY, size=13, weight="bold"),
            text_color=c["text_primary"]
        ).pack(side="left")

        self.ver_dot1_lbl = ctk.CTkLabel(
            r2, text="  Blink 1", image=self._dot_off, compound="left",
            font=ctk.CTkFont(family=FluentTheme.FONT_FAMILY, size=13, weight="bold"),
            text_color=c["text_secondary"]
        )
        self.ver_dot1_lbl.pack(side="left", padx=(12, 24))

        self.ver_dot2_lbl = ctk.CTkLabel(
            r2, text="  Blink 2", image=self._dot_off, compound="left",
            font=ctk.CTkFont(family=FluentTheme.FONT_FAMILY, size=13, weight="bold"),
            text_color=c["text_secondary"]
        )
        self.ver_dot2_lbl.pack(side="left")

        self.ver_status_lbl = ctk.CTkLabel(
            self.ver_stage_card,
            text='STATUS:  "Scanning... Please blink naturally twice"',
            font=ctk.CTkFont(family=FluentTheme.FONT_FAMILY, size=13, weight="bold"),
            text_color=c["text_primary"]
        )
        self.ver_status_lbl.pack(side="bottom", pady=(2, 4))

        cam_host = ctk.CTkFrame(self.ver_stage_card, fg_color=c["input_bg"], corner_radius=8)
        cam_host.pack(side="top", fill="both", expand=True, padx=10, pady=(8, 4))
        cam_host.pack_propagate(False)

        self.ver_cam_lbl = ctk.CTkLabel(cam_host, text="Opening Camera...", fg_color="transparent")
        self.ver_cam_lbl.pack(fill="both", expand=True)

        self._start_embedded_camera(self.ver_cam_lbl, cam_host, mode="verify")

    def _tick_verification_integer_timer(self):
        if self.active_nav != "verify_demo" or not hasattr(self, "ver_timer_lbl") or not self.ver_timer_lbl.winfo_exists():
            return
        if not getattr(self, "_ver_timer_paused", False):
            if self._ver_seconds > 0:
                self.ver_timer_lbl.configure(text=f"Time: {self._ver_seconds}s", text_color=self.accent)
                self._ver_seconds -= 1
            else:
                if getattr(self, "_verify_mode_purpose", "ITEM_UNLOCK") == "APP_STARTUP":
                    owner = None
                else:
                    target_item = getattr(self, "_current_unlock_target", None)
                    owner = target_item["owner"] if target_item else self.active_user
                diag = self.bio_engine.build_timeout_diagnostic(expected_owner=owner)
                self._show_verification_error_card(
                    reason_title=diag["reason_title"],
                    explanation=diag["explanation"],
                    face_item=diag["face_item"],
                    pulse_item=diag["pulse_item"],
                    blink_item=diag["blink_item"]
                )
                return
        else:
            self.ver_timer_lbl.configure(text=f"Time: {self._ver_seconds}s (Paused)", text_color=self.colors["warning"])

        self.after(1000, self._tick_verification_integer_timer)

    def _apply_ver_sim_state(self, state_code: str):
        self._manual_sim_override = True
        c = self.colors
        # If switching back to a live camera state from an Error Card, rebuild live stage
        if state_code.startswith("LIVE") or state_code.startswith("WARN"):
            if not hasattr(self, "ver_status_lbl") or not self.ver_status_lbl.winfo_exists():
                self._build_live_verification_stage()

        if state_code == "LIVE_SCAN":
            self._ver_timer_paused = False
            self._cam_oval_color = (56, 189, 248)
            self.ver_timer_lbl.configure(text=f"Time: {max(1, self._ver_seconds)}s", text_color=self.accent)
            self.ver_status_lbl.configure(
                text='STATUS:  "Scanning... Please blink naturally twice"', text_color=c["text_primary"]
            )
            self.ver_prog_bar.set(0.74)
            self.ver_pct_lbl.configure(text="74%", text_color=self.accent)
            # UPDATED: Blink 1 Green, Blink 2 Slate Grey
            self.ver_dot1_lbl.configure(image=self._dot_on, text_color=c["success"])
            self.ver_dot2_lbl.configure(image=self._dot_off, text_color=c["text_secondary"])

        elif state_code == "WARN_LIGHT":
            self._ver_timer_paused = True
            self._cam_oval_color = (251, 191, 36)
            self.ver_timer_lbl.configure(text=f"Time: {self._ver_seconds}s (Paused)", text_color=c["warning"])
            self.ver_status_lbl.configure(
                text='STATUS:  "⚠ Low light detected — Please improve lighting condition"',
                text_color=c["warning"]
            )

        elif state_code == "WARN_EYES":
            self._ver_timer_paused = False
            self._cam_oval_color = (248, 113, 113)
            self.ver_status_lbl.configure(
                text='STATUS:  "✖ PLEASE OPEN YOUR EYES TO PROCEED"',
                text_color=c["danger"]
            )

        elif state_code == "WARN_MULTI":
            self._ver_timer_paused = False
            self._cam_oval_color = (248, 113, 113)
            self.ver_status_lbl.configure(
                text='STATUS:  "🚨 Multiple faces detected — Progress reset for security!"',
                text_color=c["danger"]
            )
            self.ver_prog_bar.set(0.0)
            self.ver_pct_lbl.configure(text="0%", text_color=c["danger"])
            # UPDATED: Reset both blink dots to Slate Grey
            self.ver_dot1_lbl.configure(image=self._dot_off, text_color=c["text_secondary"])
            self.ver_dot2_lbl.configure(image=self._dot_off, text_color=c["text_secondary"])

        elif state_code == "ERR_IDENTITY":
            self._show_verification_error_card(
                reason_title="REASON: IDENTITY NOT MATCHED",
                explanation="The scanned face does not match registered vault owner 'Rahul' (or Ocular Geometry check failed).",
                face_item="[ ✖ ] Not Matched",
                pulse_item="[ ✔ ] Passed",
                blink_item="[ ✔ ] Passed (2/2)"
            )
        elif state_code == "ERR_SPOOF":
            self._show_verification_error_card(
                reason_title="REASON: LIVENESS CHECK FAILED (SPOOF OR POOR LIGHT)",
                explanation="Face matched 'Rahul', but biological optical pulse liveness could not be verified.",
                face_item="[ ✔ ] Matched (Rahul)",
                pulse_item="[ ✖ ] Failed / Static",
                blink_item="[ ✔ ] Passed (2/2)"
            )
        elif state_code == "ERR_BLINK":
            self._show_verification_error_card(
                reason_title="REASON: BLINK CHALLENGE INCOMPLETE",
                explanation="Recorded only 1 of 2 required natural blinks before the 10s verification gate expired.",
                face_item="[ ✔ ] Matched (Rahul)",
                pulse_item="[ ✔ ] Passed",
                blink_item="[ ✖ ] Incomplete (1/2)"
            )
        elif state_code == "ERR_OWNER":
            self._show_verification_error_card(
                reason_title="REASON: WRONG VAULT OWNER",
                explanation="Identity verified as 'Aman', but this vault is locked exclusively by 'Rahul'.",
                face_item="[ ✖ ] Wrong Owner (Aman)",
                pulse_item="[ ✔ ] Passed",
                blink_item="[ ✔ ] Passed (2/2)"
            )


    def _show_verification_error_card(
        self, reason_title: str, explanation: str, face_item: str, pulse_item: str, blink_item: str
    ):
        """Replaces the live camera viewport with the Terminal Diagnostic Error Card at Time: 0s."""
        self._stop_active_camera()
        self._ver_timer_paused = True
        c = self.colors
        self.ver_timer_lbl.configure(text="Time: 0s", text_color=c["danger"])

        for w in self.ver_stage_card.winfo_children():
            w.destroy()

        err_box = ctk.CTkFrame(
            self.ver_stage_card, fg_color=c["input_bg"],
            border_width=1, border_color=c["danger"], corner_radius=12
        )
        err_box.pack(expand=True, fill="x", padx=95, pady=24)

        ctk.CTkLabel(
            err_box, text="[ ✖ ]  ACCESS DENIED",
            font=ctk.CTkFont(family=FluentTheme.FONT_FAMILY, size=19, weight="bold"),
            text_color=c["danger"]
        ).pack(pady=(18, 6))

        ctk.CTkLabel(
            err_box, text=reason_title,
            font=ctk.CTkFont(family=FluentTheme.FONT_FAMILY, size=14, weight="bold"),
            text_color=c["text_primary"]
        ).pack(pady=(0, 4))

        ctk.CTkLabel(
            err_box, text=explanation, wraplength=440,
            font=ctk.CTkFont(family=FluentTheme.FONT_FAMILY, size=12),
            text_color=c["text_secondary"]
        ).pack(padx=24, pady=(0, 14))

        # Checklist Breakdown
        chk = ctk.CTkFrame(err_box, fg_color=c["card_bg"], corner_radius=8)
        chk.pack(fill="x", padx=40, pady=(0, 16))

        for label, status in [
            ("Face & Ocular Identity:", face_item),
            ("Optical Liveness Check:", pulse_item),
            ("Blink Challenge (2/2):",  blink_item),
        ]:
            row = ctk.CTkFrame(chk, fg_color="transparent")
            row.pack(fill="x", padx=16, pady=5)
            ctk.CTkLabel(
                row, text=f"•  {label}",
                font=ctk.CTkFont(family=FluentTheme.FONT_FAMILY, size=12, weight="bold"),
                text_color=c["text_secondary"]
            ).pack(side="left")
            is_pass = "[ ✔ ]" in status
            ctk.CTkLabel(
                row, text=status,
                font=ctk.CTkFont(family=FluentTheme.FONT_FAMILY, size=12, weight="bold"),
                text_color=c["success"] if is_pass else c["danger"]
            ).pack(side="right")

        btn_row = ctk.CTkFrame(err_box, fg_color="transparent")
        btn_row.pack(pady=(0, 18))

        ctk.CTkButton(
            btn_row, text="↻  Try Scan Again", width=155, height=36, corner_radius=8,
            fg_color=self.accent, hover_color=self.accent_hover, text_color="#FFFFFF",
            font=ctk.CTkFont(family=FluentTheme.FONT_FAMILY, size=13, weight="bold"),
            command=lambda: [setattr(self, "_ver_seconds", 30), self._apply_ver_sim_state("LIVE_SCAN")]
        ).pack(side="left", padx=8)

        ctk.CTkButton(
            btn_row, text="✕  Close", width=110, height=36, corner_radius=8,
            fg_color=c["card_hover"], text_color=c["text_primary"],
            command=lambda: self.switch_screen("dashboard")
        ).pack(side="left", padx=8)


if __name__ == "__main__":
    import traceback
    try:
        app = BioVaultSampleApp()
        app.report_callback_exception = lambda exc_type, exc_value, exc_traceback: traceback.print_exception(exc_type, exc_value, exc_traceback)
        app.mainloop()
    except Exception as e:
        print("Fatal error occurred:", e)
        traceback.print_exc()
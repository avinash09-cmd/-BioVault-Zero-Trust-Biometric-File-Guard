import os
import json
import time
import hashlib
import subprocess
from typing import Any


class VaultStorageAndLockPipeline:
    def __init__(self, base_dir: str | None = None) -> None:
        if base_dir is None:
            base_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "biovault_data")
        self.base_dir = base_dir
        self.profiles_dir = os.path.join(self.base_dir, "profiles")
        self.state_file = os.path.join(self.base_dir, "vault_state.json")

        os.makedirs(self.profiles_dir, exist_ok=True)
        self.state: dict[str, Any] = self._load_state()

    def _default_state(self) -> dict[str, Any]:
        return {
            "users": [],
            "locked_items": [],
            "recovery_password_salt": None,
            "recovery_password_hash": None,
            "settings": {
                "theme": "Dark",
                "accent": "Fluent Blue",
                "auto_relock_minutes": 5,
                "minimize_to_tray": True,
                "auto_start": False,
                "ctx_menu": True,
                "win11_direct": True,
            },
        }

    def _load_state(self) -> dict[str, Any]:
        if not os.path.exists(self.state_file):
            st = self._default_state()
            self._write_json(st)
            return st
        try:
            with open(self.state_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            default = self._default_state()
            for k, v in default.items():
                if k not in data:
                    data[k] = v
            return data
        except Exception:
            return self._default_state()

    def _write_json(self, data: dict[str, Any]) -> None:
        try:
            with open(self.state_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"[vault_locker.py] Failed to save state: {e}")

    def save_state(self) -> None:
        self._write_json(self.state)

    # ==========================================================================
    # USER & RECOVERY PASSWORD MANAGEMENT
    # ==========================================================================

    def add_user_record(self, username: str) -> None:
        for u in self.state["users"]:
            if str(u.get("name", "")).lower() == username.lower():
                u["enrolled"] = time.strftime("%d %b %Y, %H:%M")
                self.save_state()
                return
        self.state["users"].append({
            "name": username,
            "enrolled": time.strftime("%d %b %Y, %H:%M"),
            "samples": "12 Poses (512-D)",
            "ocular": "4-Ratio Ocular",
        })
        self.save_state()

    def remove_user_record(self, username: str) -> None:
        self.state["users"] = [
            u for u in self.state["users"]
            if str(u.get("name", "")).lower() != username.lower()
        ]
        self.save_state()

    def has_recovery_password(self) -> bool:
        return bool(self.state.get("recovery_password_hash"))

    def set_recovery_password(self, raw_password: str) -> None:
        salt = os.urandom(16).hex()
        dk = hashlib.pbkdf2_hmac("sha256", raw_password.encode("utf-8"), salt.encode("utf-8"), 120_000).hex()
        self.state["recovery_password_salt"] = salt
        self.state["recovery_password_hash"] = dk
        self.save_state()

    def verify_recovery_password(self, raw_password: str) -> bool:
        salt = self.state.get("recovery_password_salt")
        expected = self.state.get("recovery_password_hash")
        if not salt or not expected:
            return False
        dk = hashlib.pbkdf2_hmac("sha256", raw_password.encode("utf-8"), str(salt).encode("utf-8"), 120_000).hex()
        return dk == expected

    # ==========================================================================
    # NTFS ICACLS LOCKING, TIMED BATCH UNLOCK & AUTO-RELOCK
    # ==========================================================================

    def lock_path_ntfs(self, target_path: str, owner_name: str) -> tuple[bool, str]:
        abs_path = os.path.normpath(os.path.abspath(target_path))
        if not os.path.exists(abs_path):
            return False, f"Path does not exist: {abs_path}"

        for existing in self.state["locked_items"]:
            if os.path.normcase(str(existing.get("path", ""))) == os.path.normcase(abs_path):
                return False, "This folder or file is already protected inside BioVault."

        is_dir = os.path.isdir(abs_path)
        cmd = f'icacls "{abs_path}" /inheritance:d /deny *S-1-1-0:(OI)(CI)(F) /c /q' if is_dir else f'icacls "{abs_path}" /inheritance:d /deny *S-1-1-0:(F) /c /q'
        res = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        if res.returncode != 0:
            return False, f"NTFS icacls lock failed: {res.stderr.strip() or res.stdout.strip()}"

        now_str = time.strftime("%d %b %Y, %H:%M")
        self.state["locked_items"].insert(0, {
            "name": os.path.basename(abs_path) or abs_path,
            "path": abs_path,
            "is_dir": is_dir,
            "type": "folder" if is_dir else "file",
            "owner": owner_name,
            "status": "locked",
            "locked_at": now_str,
            "date": now_str,
        })
        self.save_state()
        return True, f"Locked '{os.path.basename(abs_path)}' via NTFS ACL."

    def unlock_path_ntfs(self, target_path: str) -> tuple[bool, str]:
        """Unlocks a specific path via NTFS icacls and marks its status as 'unlocked'."""
        abs_path = os.path.normpath(os.path.abspath(target_path))
        if os.path.exists(abs_path):
            cmd = f'icacls "{abs_path}" /reset /c /q'
            res = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            if res.returncode != 0:
                return False, f"NTFS icacls unlock failed: {res.stderr.strip() or res.stdout.strip()}"

        for item in self.state["locked_items"]:
            if os.path.normcase(str(item.get("path", ""))) == os.path.normcase(abs_path):
                item["status"] = "unlocked"

        self.save_state()
        return True, f"Unlocked '{os.path.basename(abs_path)}'."
    
    def unlock_all_for_owner(self, owner_name: str) -> tuple[int, str]:
        unlocked_count = 0
        for item in self.state["locked_items"]:
            if str(item.get("owner", "")).lower() == owner_name.lower():
                path = str(item.get("path", ""))
                if os.path.exists(path):
                    cmd = f'icacls "{path}" /reset /c /q'
                    subprocess.run(cmd, shell=True, capture_output=True, text=True)
                item["status"] = "unlocked"
                unlocked_count += 1
        self.save_state()
        return unlocked_count, f"Temporarily unlocked {unlocked_count} item(s) for {owner_name}."

    def relock_all_for_owner(self, owner_name: str) -> int:
        relocked_count = 0
        for item in self.state["locked_items"]:
            if str(item.get("owner", "")).lower() == owner_name.lower():
                path = str(item.get("path", ""))
                is_dir = bool(item.get("is_dir", True))
                if os.path.exists(path):
                    cmd = f'icacls "{path}" /inheritance:d /deny *S-1-1-0:(OI)(CI)(F) /c /q' if is_dir else f'icacls "{path}" /inheritance:d /deny *S-1-1-0:(F) /c /q'
                    subprocess.run(cmd, shell=True, capture_output=True, text=True)
                item["status"] = "locked"
                relocked_count += 1
        self.save_state()
        return relocked_count

    def relock_all_temporarily_unlocked(self) -> None:
        changed = False
        for item in self.state["locked_items"]:
            if item.get("status") == "unlocked":
                path = str(item.get("path", ""))
                is_dir = bool(item.get("is_dir", True))
                if os.path.exists(path):
                    cmd = f'icacls "{path}" /inheritance:d /deny *S-1-1-0:(OI)(CI)(F) /c /q' if is_dir else f'icacls "{path}" /inheritance:d /deny *S-1-1-0:(F) /c /q'
                    subprocess.run(cmd, shell=True, capture_output=True, text=True)
                item["status"] = "locked"
                changed = True
        if changed:
            self.save_state()

    def remove_item_permanently(self, target_path: str) -> tuple[bool, str]:
        abs_path = os.path.normpath(os.path.abspath(target_path))
        if os.path.exists(abs_path):
            cmd = f'icacls "{abs_path}" /reset /c /q'
            subprocess.run(cmd, shell=True, capture_output=True, text=True)
        self.state["locked_items"] = [
            it for it in self.state["locked_items"]
            if os.path.normcase(str(it.get("path", ""))) != os.path.normcase(abs_path)
        ]
        self.save_state()
        return True, "Removed NTFS lock permanently."
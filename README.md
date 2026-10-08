# 🛡️ BioVault — Zero-Trust Biometric File Guard


![Platform](https://img.shields.io/badge/Platform-Windows%2010%20%7C%2011%20(x64)-0078D6?style=for-the-badge&logo=windows)
![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?style=for-the-badge&logo=python&logoColor=white)
![OpenCV](https://img.shields.io/badge/OpenCV-Computer%20Vision-5C3EE8?style=for-the-badge&logo=opencv&logoColor=white)
![Security](https://img.shields.io/badge/Security-NTFS%20ACL%20%2B%20PBKDF2-10B981?style=for-the-badge)


**BioVault** is an offline, Windows 11 Fluent-styled biometric file and folder locking utility[span_0](start_span)[span_0](end_span). Instead of relying on cloud servers or simple 2D face snapshots, BioVault combines **3-stage biometric verification** (Facial & Ocular Identity, Optical rPPG Liveness, and a 2D Iris-Disc Blink Challenge)[span_1](start_span)[span_1](end_span)[span_2](start_span)[span_2](end_span) with **OS-level Windows NTFS Access Control Lists (`icacls`)** to protect sensitive files directly on your disk[span_3](start_span)[span_3](end_span)[span_4](start_span)[span_4](end_span)[span_5](start_span)[span_5](end_span)[span_6](start_span)[span_6](end_span).


---


## ✨ Key Features


### 🔒 1. 3-Stage Zero-Trust Biometric Verification
Standard webcam logins can be spoofed with a photo or smartphone video. BioVault enforces a strict, sequential 3-stage verification pipeline before unlocking any data[span_7](start_span)[span_7](end_span)[span_8](start_span)[span_8](end_span):
* **Stage 1 — Facial & Ocular Identity (0% → 45%):** Matches 512-D facial embeddings (via InsightFace `buffalo_l` or normalized periocular fallback) alongside a 4-Ratio Ocular Geometry signature[span_9](start_span)[span_9](end_span)[span_10](start_span)[span_10](end_span)[span_11](start_span)[span_11](end_span).
* **Stage 2 — Forehead Optical Pulse Liveness (45% → 60%):** Samples green-channel micro-variance across the forehead region (rPPG) to verify biological skin liveness[span_12](start_span)[span_12](end_span)[span_13](start_span)[span_13](end_span).
* **Stage 3 — 2D Iris-Disc Blink Challenge (60% → 100%):** Tracks a scale-normalized `48x24` eye grid with nose-bridge luma reference to detect hand obstructions and require two natural blinks[span_14](start_span)[span_14](end_span)[span_15](start_span)[span_15](end_span).


### 🧬 2. 5-Step Guided Biometric Registration Studio
* Captures **12 multi-angle pose snapshots** across 4 buckets (*Center, Turn Left, Turn Right, Lift Chin*) plus **2 liveness blinks** to seal the profile[span_16](start_span)[span_16](end_span)[span_17](start_span)[span_17](end_span)[span_18](start_span)[span_18](end_span).
* **Live Hardware Quality Gates:** Real-time checks for sitting distance (`Too Far` / `Too Close`), room lighting, strong backlighting, eye socket obstructions/glare, and multiple faces in frame[span_19](start_span)[span_19](end_span)[span_20](start_span)[span_20](end_span)[span_21](start_span)[span_21](end_span).


### 🛡️ 3. OS-Level NTFS File & Folder Locking
* Locks files and directories at the file-system level using Windows `icacls` (`*S-1-1-0:(OI)(CI)(F)` deny rules with inheritance disabled)[span_22](start_span)[span_22](end_span)[span_23](start_span)[span_23](end_span)[span_24](start_span)[span_24](end_span).
* **Multi-User Vault Isolation:** Supports multiple enrolled biometric profiles on the same PC[span_25](start_span)[span_25](end_span)[span_26](start_span)[span_26](end_span)[span_27](start_span)[span_27](end_span). Each user only sees and unlocks files protected under their own profile[span_28](start_span)[span_28](end_span).
* **Auto-Relock Lease Timer:** Temporarily unlocks a user's files for a configurable duration (**1, 5, 10, 15, 30, or 60 minutes**) and automatically re-applies NTFS locks when the timer expires or when the app exits[span_29](start_span)[span_29](end_span).


### 🔑 4. Fail-Safe Emergency Recovery Password
* Enforces a mandatory **Emergency Recovery Password** before locking your first item so broken webcams or pitch-dark rooms never lock you out[span_30](start_span)[span_30](end_span).
* Hashed locally using **PBKDF2-HMAC-SHA256** with a 16-byte random cryptographic salt and 120,000 iterations[span_31](start_span)[span_31](end_span)[span_32](start_span)[span_32](end_span)[span_33](start_span)[span_33](end_span).


### 🖥️ 5. Deep Windows 11 Shell & Fluent UI Integration
* **Windows Explorer Context Menu:** Right-click any file or folder in Windows Explorer and select **"Lock with BioVault"** or **"Unlock with BioVault"** (registered under `HKCU\Software\Classes` — zero Administrator privileges required)[span_34](start_span)[span_34](end_span).
* **System Tray Background Mode:** Minimize BioVault silently to the Windows System Tray with quick actions to open the vault or immediately relock all unlocked items[span_35](start_span)[span_35](end_span)[span_36](start_span)[span_36](end_span).
* **Customizable Fluent Design UI:** Built with `CustomTkinter` featuring a borderless Windows 11 caption bar, **Dark / Light / System** theme syncing, and 4 custom accent palettes (*Fluent Blue, Power Purple, Emerald Guard, Amber Shield*)[span_37](start_span)[span_37](end_span).


---


## 📂 Project Architecture


```text
BioVault/
├── biovault_ui_sample.py    # Main WinUI 3 / Fluent Desktop GUI, Camera Threads & Screens
├── biometric_engine.py      # 3-Stage Verification, 5-Step Enrollment & 2D Iris-Disc Blink Engine
├── vault_locker.py          # NTFS icacls Locking Pipeline, PBKDF2 Recovery Crypto & JSON State
├── system_integration.py    # Windows Registry Context Menu, System Tray & Dynamic .ICO Generator
└── setup_msi.py             # cx_Freeze Standalone Windows .MSI Installer Build Script
```


### 🔐 Local Data & Privacy (`100% Offline`)
BioVault never transmits camera frames or biometric templates over the network.
* **Installed App Mode (`.msi` / `.exe`):** Data is stored safely inside `%LOCALAPPDATA%\BioVault\biovault_data`[span_38](start_span)[span_38](end_span)[span_39](start_span)[span_39](end_span)[span_40](start_span)[span_40](end_span).
* **Developer Script Mode (`.py`):** Data is stored inside `./biovault_data/`[span_41](start_span)[span_41](end_span)[span_42](start_span)[span_42](end_span)[span_43](start_span)[span_43](end_span)[span_44](start_span)[span_44](end_span)[span_45](start_span)[span_45](end_span).
* Biometric templates are stored as compressed NumPy archives (`profiles/<username>.npz`), and vault metadata is tracked in `vault_state.json`[span_46](start_span)[span_46](end_span)[span_47](start_span)[span_47](end_span)[span_48](start_span)[span_48](end_span)[span_49](start_span)[span_49](end_span)[span_50](start_span)[span_50](end_span).


---


## 🚀 Getting Started


### Option A: End-User Installation (`.msi` Installer)
1. Download the latest **`BioVault-1.0.0-win64.msi`** installer from the `dist/` folder (or Releases page).
2. Double-click the `.msi` file to install BioVault to `%LOCALAPPDATA%\Programs\BioVault`[span_51](start_span)[span_51](end_span).
3. Launch **BioVault** from your **Desktop** or **Windows Start Menu** shortcut.


---


### Option B: Run from Source (Developers)


#### 1. Prerequisites
* **OS:** Windows 10 or Windows 11 (64-bit)
* **Python:** Python 3.10 – 3.13
* **Hardware:** Integrated laptop webcam or external USB camera[span_52](start_span)[span_52](end_span)


#### 2. Install Dependencies
```bash
pip install opencv-python numpy Pillow customtkinter darkdetect pystray cx_Freeze
```
*(Optional)* For 512-D ArcFace neural embeddings via InsightFace:
```bash
pip install insightface onnxruntime
```


#### 3. Run the Application
```bash
python biovault_ui_sample.py
```


---


## 📦 Building the Standalone `.msi` Installer


BioVault uses **`cx_Freeze`** to compile the Python environment, bundle `CustomTkinter` assets and OpenCV Haar Cascades, embed the custom Shield-Scanner `.ico` file, and generate a native Windows `.msi` package.


Run the following command in the project root:


```bash
python setup_msi.py bdist_msi
```


* **Compiled Portable Executable:** `build/exe.win-amd64-<version>/BioVault.exe`
* **Distributable Windows Installer:** `dist/BioVault-1.0.0-win64.msi`


---


## 📖 Quick Usage Guide


1. **Enroll Your Biometric Profile:**
   * Open BioVault and click **+ Register Biometric Profile**[span_53](start_span)[span_53](end_span).
   * Enter your profile name, align your face inside the camera frame, follow the 4 pose prompts (*Center, Left, Right, Lift Chin*), and **blink naturally twice** to seal your profile[span_54](start_span)[span_54](end_span)[span_55](start_span)[span_55](end_span)[span_56](start_span)[span_56](end_span).
2. **Set Your Emergency Recovery Password:**
   * When locking your first file or folder, enter and confirm a recovery password (minimum 4 characters)[span_57](start_span)[span_57](end_span).
3. **Lock Files or Folders:**
   * **In-App:** Click **+ Lock Folder** or **+ Lock File** on the Vault Dashboard[span_58](start_span)[span_58](end_span).
   * **From Windows Explorer:** Right-click any file or folder and click **Lock with BioVault**[span_59](start_span)[span_59](end_span).
4. **Unlock & Auto-Relock:**
   * Click **Unlock** on any protected item (or right-click it in Explorer and choose **Unlock with BioVault**)[span_60](start_span)[span_60](end_span)[span_61](start_span)[span_61](end_span).
   * Complete the 3-stage face and blink scan (or use your Emergency Recovery Password)[span_62](start_span)[span_62](end_span)[span_63](start_span)[span_63](end_span)[span_64](start_span)[span_64](end_span).
   * Your items unlock for the active lease duration (default **5 minutes**) and automatically relock when the countdown finishes or when you click **Relock Now**[span_65](start_span)[span_65](end_span)[span_66](start_span)[span_66](end_span)[span_67](start_span)[span_67](end_span)[span_68](start_span)[span_68](end_span).


---


## 🛠️ Command-Line Arguments (Explorer Integration)


`BioVault.exe` (and `biovault_ui_sample.py`) accepts CLI flags used by the Windows Explorer right-click shell extensions[span_69](start_span)[span_69](end_span)[span_70](start_span)[span_70](end_span):


```bash
# Trigger biometric verification and lock a target file or folder
BioVault.exe --lock "C:\Path\To\SecretFolder"


# Trigger biometric verification and unlock a protected file or folder
BioVault.exe --unlock "C:\Path\To\SecretFolder"
```

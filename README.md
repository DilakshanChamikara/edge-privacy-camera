# Edge Privacy Camera

![Python](https://img.shields.io/badge/Python-3.11+-blue)
![Platform](https://img.shields.io/badge/Platform-Raspberry%20Pi%205-red)
![AI Accelerator](https://img.shields.io/badge/AI%20Accelerator-Hailo--10H-green)
![License](https://img.shields.io/badge/License-Apache--2.0-blue)

**Raspberry Pi 5 and Hailo-10H based edge AI camera system for local face detection, real-time face blurring, and privacy-preserving video recording.**

Edge Privacy Camera is a research prototype designed for shared living spaces such as shared apartments, student housing, and co-living environments. The system detects faces locally on the device and applies face blurring before video is recorded, reducing unnecessary facial exposure while keeping useful security context.

This project was developed as part of a Master's thesis at Stockholm University in the field of Human-Computer Interaction and Human-Centred Cybersecurity.

---

## Overview

Home security cameras can improve safety, but in shared homes they can also create privacy concerns. A camera installed by one person may record residents, guests, friends, service workers, or visitors who do not directly control the device.

This project explores a privacy-first alternative. Instead of sending footage to the cloud or storing raw identifiable video, the system processes video locally on a Raspberry Pi 5 with a Hailo-10H AI accelerator. Faces are detected and blurred before the video frame is written to storage.

The main goal is simple:

> Preserve useful security awareness while reducing unnecessary facial exposure.

---

## Key Features

| Feature                      | Description                                                                  |
| ---------------------------- | ---------------------------------------------------------------------------- |
| **Edge AI processing**       | Runs face detection and recognition locally on Raspberry Pi 5 with Hailo-10H |
| **Real-time face blurring**  | Applies blurring before frames are recorded                                  |
| **Three privacy modes**      | Supports Blur All, Blur Owners, and Blur Guests modes                        |
| **Local-first design**       | No cloud processing is required for detection, recognition, or blurring      |
| **Encrypted enrolment data** | Face images and embeddings are encrypted using AES-256-GCM                   |
| **PIN-based access**         | A 4-digit PIN is used to unlock the system and derive the encryption key     |
| **GUI launcher**             | Tkinter-based interface for registration, enrolment, and mode selection      |
| **External drive support**   | Automatically records to an external drive when available                    |
| **Recording rotation**       | Organises video files by date and rotates recordings automatically           |
| **Frame-skip optimisation**  | Improves real-time performance using detection intervals and interpolation   |
| **Graceful recovery**        | Includes recovery handling for camera and Hailo inference errors             |

---

## Privacy Modes

The system supports three operating modes.

### 1. Blur All Faces

Every detected face is blurred, regardless of identity.

This mode provides the strongest privacy protection because all detected people are anonymised before recording.

### 2. Blur Owners

Only enrolled residents or owners are blurred. Unknown people remain visible.

This mode is useful when residents want to protect their own privacy while keeping unknown people visible for security review.

### 3. Blur Guests

All non-enrolled people are blurred, while enrolled residents remain visible.

This mode is useful when guest privacy is important, such as when friends, visitors, service workers, or temporary guests enter a shared home.

---

## System Architecture

The system follows a local privacy-preserving pipeline:

```text
Camera frame
    |
    |-- Raw frame exists only in memory during processing
    |
Face detection using SCRFD-2.5G
    |
Optional face recognition using ArcFace MobileFaceNet
    |
Centroid tracking and identity smoothing
    |
Face blurring on copied frame
    |
Display and record processed frame
```

The main privacy boundary is placed before recording. The recorder receives the processed frame after the blurring step.

---

## Hardware Requirements

The project was developed and tested with the following hardware:

* Raspberry Pi 5
* Hailo-10H AI accelerator
* Raspberry Pi M.2 HAT+ or compatible Hailo connection board
* Raspberry Pi Camera Module 3 or compatible camera
* External USB storage device for recordings
* Display, keyboard, and mouse for setup and GUI use

---

## Software Requirements

Recommended environment:

* Raspberry Pi OS Bookworm
* Python 3.11+
* HailoRT 5.1.1+
* OpenCV
* Picamera2
* Tkinter
* Python `cryptography` package

Install the main dependencies:

```bash
sudo apt update
sudo apt install hailo-all python3-opencv python3-picamera2 python3-tk
pip install cryptography
```

Using a Python virtual environment is recommended, especially if your Raspberry Pi has multiple Python projects.

---

## Repository Structure

```text
edge-privacy-camera/
├── launcher.py
├── hailo_utils.py
├── hailo_enroll.py
├── hailo_face_blur_all.py
├── hailo_face_blur_owners.py
├── hailo_face_blur_guests.py
├── image_capture.py
├── crypto_utils.py
├── pin_manager.py
├── download_models.sh
├── run.sh
├── FaceDetection.desktop
├── models/
├── facedata/
├── encodings/
├── config/
└── recordings/
```

### Main Files

| File                        | Purpose                                                                                  |
| --------------------------- | ---------------------------------------------------------------------------------------- |
| `launcher.py`               | GUI launcher with PIN authentication, task control, and privacy mode selection           |
| `hailo_utils.py`            | Shared camera, Hailo inference, tracking, recognition, recording, and blurring utilities |
| `hailo_enroll.py`           | Builds encrypted face embedding databases from face images                               |
| `hailo_face_blur_all.py`    | Runs Blur All Faces mode                                                                 |
| `hailo_face_blur_owners.py` | Runs Blur Owners mode                                                                    |
| `hailo_face_blur_guests.py` | Runs Blur Guests mode                                                                    |
| `image_capture.py`          | Captures encrypted face images for enrolment                                             |
| `crypto_utils.py`           | Handles AES-256-GCM encryption, PIN verification, and key derivation                     |
| `pin_manager.py`            | Command-line tool for PIN setup, change, status check, and factory reset                 |
| `download_models.sh`        | Downloads Hailo-compiled model files                                                     |
| `run.sh`                    | Shell script for launching the GUI on Raspberry Pi                                       |
| `FaceDetection.desktop`     | Optional Raspberry Pi desktop shortcut                                                   |

---

## Model Files

The system uses two Hailo-compiled HEF models.

| Model                       | Task           | Input Size    | Output                              |
| --------------------------- | -------------- | ------------- | ----------------------------------- |
| `scrfd_2.5g.hef`            | Face detection | 640 × 640 × 3 | Bounding boxes and facial landmarks |
| `arcface_mobilefacenet.hef` | Face embedding | 112 × 112 × 3 | 512-dimensional embedding vector    |

Download the models using:

```bash
chmod +x download_models.sh
./download_models.sh
```

If automatic download is not available, place the required model files in the `models/` directory:

```text
models/
├── scrfd_2.5g.hef
└── arcface_mobilefacenet.hef
```

---

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/DilakshanChamikara/edge-privacy-camera.git
cd edge-privacy-camera
```

### 2. Install dependencies

```bash
sudo apt update
sudo apt install hailo-all python3-opencv python3-picamera2 python3-tk
pip install cryptography
```

### 3. Download or copy the model files

```bash
chmod +x download_models.sh
./download_models.sh
```

Check that the model files exist:

```bash
ls models/
```

Expected files:

```text
scrfd_2.5g.hef
arcface_mobilefacenet.hef
```

### 4. Verify the Hailo device

```bash
hailortcli fw-control identify
```

The output should confirm that a Hailo-10H device is available.

### 5. Start the system

```bash
python3 launcher.py
```

Or run:

```bash
./run.sh
```

---

## First-Time Setup

On first launch, the system asks the user to create a 4-digit PIN.

This PIN is used to derive an AES-256 encryption key using scrypt. The PIN itself is not stored directly. The derived key is used to encrypt and decrypt sensitive files such as captured face images and face embedding databases.

After unlocking, the GUI provides actions for:

1. Registering faces using the camera
2. Uploading face images
3. Enrolling face embeddings
4. Running Blur All mode
5. Running Blur Owners mode
6. Running Blur Guests mode
7. Changing the PIN

---

## PIN and Encryption

Sensitive biometric data is encrypted using AES-256-GCM.

Encrypted files include:

* Captured face images
* Uploaded face images
* Face embedding pickle files
* PIN verification token

Encryption workflow:

```text
4-digit PIN
    |
scrypt key derivation
    |
256-bit AES key
    |
AES-256-GCM encryption
    |
Encrypted face images and embeddings
```

PIN management commands:

```bash
python3 pin_manager.py --status
python3 pin_manager.py --setup
python3 pin_manager.py --change
python3 pin_manager.py --factory-reset
```

Changing the PIN re-encrypts existing encrypted files with the new key.

Factory reset removes the PIN configuration, encrypted enrolment files, and encrypted captured face data.

---

## Usage

### Launch the GUI

```bash
python3 launcher.py
```

The GUI is the recommended way to use the system.

### Capture Face Images

```bash
python3 image_capture.py
```

Controls:

```text
SPACE  Capture image
q      Quit
```

Captured images are encrypted before being saved.

### Enrol Faces

```bash
python3 hailo_enroll.py
```

This creates encrypted face embedding files from the available face images.

### Run Blur All Mode

```bash
python3 hailo_face_blur_all.py
```

Run without recording:

```bash
python3 hailo_face_blur_all.py --no-record
```

### Run Blur Owners Mode

```bash
python3 hailo_face_blur_owners.py
```

### Run Blur Guests Mode

```bash
python3 hailo_face_blur_guests.py
```

---

## Command-Line Options

Common options:

```text
--score-thresh       Face detection confidence threshold
--nms-thresh         Non-maximum suppression threshold
--detect-interval    Run detection every N frames
--no-record          Disable video recording
--record-path        Set a custom recording directory
```

Additional options for owner/guest modes:

```text
--embed-thresh       Face recognition similarity threshold
--embed-interval     Run recognition every N frames
```

Example:

```bash
python3 hailo_face_blur_owners.py --embed-thresh 0.45 --detect-interval 2
```

---

## Recording

The system records processed video frames after the blurring step.

By default, recordings are saved to an external drive if one is detected. If no external drive is available, the system falls back to the local `recordings/` directory.

Recording path priority:

1. `RECORDING_PATH` environment variable
2. `config/settings.json`
3. Auto-detected external drive under `/media` or `/mnt`
4. Local `recordings/` folder

Example `config/settings.json`:

```json
{
  "recording_path": "/media/pi/MyDrive/cctv_recordings"
}
```

Example recording structure:

```text
cctv_recordings/
└── 2026-06-03/
    ├── blurred_120000.avi
    └── blurred_123000.avi
```

---

## Face Enrolment

Face images are stored under `facedata/`.

```text
facedata/
├── camcap/       Camera-captured or uploaded resident images
├── aigen/        AI-generated reference images
└── realimages/   Additional real face reference images
```

The `camcap` folder is reprocessed when its contents change. The `aigen` and `realimages` folders are normally processed once unless their encrypted embedding files are removed.

Generated encrypted embedding files are stored in `encodings/`:

```text
encodings/
├── camcap_arcface.pickle.enc
├── aigen_arcface.pickle.enc
└── realimages_arcface.pickle.enc
```

---

## Performance Summary

In the thesis evaluation, the prototype achieved real-time performance under indoor test conditions.

| Mode                       | Models Used                        | Average FPS |
| -------------------------- | ---------------------------------- | ----------: |
| Blur All Faces             | SCRFD-2.5G                         |    12.1 FPS |
| Blur Owners                | SCRFD-2.5G + ArcFace MobileFaceNet |    13.7 FPS |
| Blur Guests                | SCRFD-2.5G + ArcFace MobileFaceNet |    19.6 FPS |
| Blur All without recording | SCRFD-2.5G                         |    16.5 FPS |

Performance may vary depending on lighting, number of visible faces, camera placement, recording drive speed, Raspberry Pi configuration, and detection/recognition intervals.

---

## Privacy and Ethical Use

This project is designed to support privacy in shared living spaces, not to enable hidden surveillance.

Before using or adapting this project:

* Inform residents and visitors that a camera system is being used.
* Explain what is recorded and what is blurred.
* Avoid recording private areas such as bedrooms and bathrooms.
* Agree on recording retention periods.
* Do not use the system to secretly monitor people.
* Follow local laws, housing rules, and institutional ethical requirements.

---

## Academic Context

This project is part of the Master's thesis:

**Designing Privacy-Preserving Home Security Camera System for Shared Living Spaces: A Human-Centered Study of Real-Time Face Blurring and Everyday Privacy**

Author: Dilakshan Chamikara Perera, Welivita Vithanalage<br>
Institution: Stockholm University<br>
Field: Human-Computer Interaction and Human-Centred Cybersecurity<br>
Year: 2026

---

## Citation

If you use or refer to this project in academic work, please cite it as:

```bibtex
@misc{Welivita_Vithanalage_Designing_Privacy-Preserving_Home_2026,
  author = {Welivita Vithanalage, Dilakshan Chamikara Perera},
  title = {{Designing Privacy-Preserving Home Security Camera System for Shared Living Spaces: A Human-Centered Study of Real-Time Face Blurring and Everyday Privacy}},
  year = {2026},
  url = {https://github.com/DilakshanChamikara/edge-privacy-camera}
}
```

---

## License

This project is licensed under the Apache License 2.0.

See the [LICENSE](LICENSE) file for details.

---

## Disclaimer

This project is a research prototype. It is not a certified security product and should not be used as the only safety or surveillance mechanism in critical environments.

The system is designed to reduce facial exposure in recorded video, but it cannot guarantee complete anonymity, perfect detection, or legal compliance in every situation.

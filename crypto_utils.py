#!/usr/bin/env python3

import os
import sys
import pickle
import getpass

from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

# paths
SCRIPT_DIR   = os.path.dirname(os.path.abspath(__file__))
CONFIG_DIR   = os.path.join(SCRIPT_DIR, "config")
SALT_PATH    = os.path.join(CONFIG_DIR, "device.salt")
VERIFY_PATH  = os.path.join(CONFIG_DIR, "pin_verify.enc")

_VERIFY_MAGIC = b"CCTV_PIN_VERIFIED_OK"
ENV_KEY_NAME = "CCTV_SESSION_KEY"

# scrypt params
_SCRYPT_N = 2 ** 14
_SCRYPT_R = 8
_SCRYPT_P = 1

MAX_ATTEMPTS = 3
LOCKOUT_MSG  = "Too many wrong attempts. Restart the application to try again."


def _derive_key(pin: str, salt: bytes) -> bytes:
    kdf = Scrypt(salt=salt, length=32, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P)
    return kdf.derive(pin.encode())


def encrypt_bytes(data: bytes, key: bytes) -> bytes:
    # nonce(12) + ciphertext + tag(16)
    nonce = os.urandom(12)
    aesgcm = AESGCM(key)
    ct = aesgcm.encrypt(nonce, data, None)
    return nonce + ct


def decrypt_bytes(data: bytes, key: bytes) -> bytes:
    if len(data) < 28:
        raise ValueError("Encrypted data too short")
    nonce = data[:12]
    ct = data[12:]
    aesgcm = AESGCM(key)
    return aesgcm.decrypt(nonce, ct, None)


def encrypt_file(src_path: str, key: bytes, dest_path: str = None,
                 delete_original: bool = True) -> str:
    if dest_path is None:
        dest_path = src_path + ".enc"
    with open(src_path, "rb") as f:
        data = f.read()
    enc = encrypt_bytes(data, key)
    with open(dest_path, "wb") as f:
        f.write(enc)
    if delete_original and src_path != dest_path:
        os.remove(src_path)
    return dest_path


def decrypt_file(enc_path: str, key: bytes) -> bytes:
    with open(enc_path, "rb") as f:
        data = f.read()
    return decrypt_bytes(data, key)


def encrypt_data_to_file(data: bytes, dest_path: str, key: bytes):
    enc = encrypt_bytes(data, key)
    with open(dest_path, "wb") as f:
        f.write(enc)


def pin_exists() -> bool:
    return os.path.exists(SALT_PATH) and os.path.exists(VERIFY_PATH)


def setup_pin(pin: str) -> bytes:
    if len(pin) != 4 or not pin.isdigit():
        raise ValueError("PIN must be exactly 4 digits")

    os.makedirs(CONFIG_DIR, exist_ok=True)

    # generate salt
    salt = os.urandom(32)
    with open(SALT_PATH, "wb") as f:
        f.write(salt)
    try:
        os.chmod(SALT_PATH, 0o600)
    except OSError:
        pass

    # derive key + store verification token
    key = _derive_key(pin, salt)
    verify_enc = encrypt_bytes(_VERIFY_MAGIC, key)
    with open(VERIFY_PATH, "wb") as f:
        f.write(verify_enc)
    try:
        os.chmod(VERIFY_PATH, 0o600)
    except OSError:
        pass

    print("[INFO] PIN configured successfully.")
    return key


def verify_pin(pin: str) -> tuple:
    if not pin_exists():
        return False, None

    with open(SALT_PATH, "rb") as f:
        salt = f.read()

    key = _derive_key(pin, salt)
    try:
        with open(VERIFY_PATH, "rb") as f:
            verify_data = f.read()
        result = decrypt_bytes(verify_data, key)
        if result == _VERIFY_MAGIC:
            return True, key
    except Exception:
        pass
    return False, None


def change_pin(old_pin: str, new_pin: str, enc_dirs: list) -> tuple:
    if len(new_pin) != 4 or not new_pin.isdigit():
        return False, "New PIN must be exactly 4 digits"

    valid, old_key = verify_pin(old_pin)
    if not valid:
        return False, "Wrong current PIN"

    new_key = setup_pin(new_pin)

    # reencrypt all .enc files with new key
    re_count = 0
    for dir_path in enc_dirs:
        if not os.path.isdir(dir_path):
            continue
        for fname in os.listdir(dir_path):
            if not fname.endswith(".enc"):
                continue
            fpath = os.path.join(dir_path, fname)
            try:
                plaintext = decrypt_bytes(
                    open(fpath, "rb").read(), old_key)
                enc = encrypt_bytes(plaintext, new_key)
                with open(fpath, "wb") as f:
                    f.write(enc)
                re_count += 1
            except Exception as e:
                print(f"[WARNING] Re-encrypt failed for {fname}: {e}")

    print(f"[INFO] PIN changed. Re-encrypted {re_count} files.")
    return True, new_key


def factory_reset():
    from hailo_utils import ENCODINGS_DIR, FACEDATA_DIR

    removed = 0
    for f in [SALT_PATH, VERIFY_PATH]:
        if os.path.exists(f):
            os.remove(f)
            removed += 1

    # delete all .enc files
    search_dirs = [
        ENCODINGS_DIR,
        os.path.join(FACEDATA_DIR, "camcap"),
    ]
    for dir_path in search_dirs:
        if not os.path.isdir(dir_path):
            continue
        for fname in os.listdir(dir_path):
            if fname.endswith(".enc"):
                os.remove(os.path.join(dir_path, fname))
                removed += 1

    # delete hash file
    hash_path = os.path.join(ENCODINGS_DIR, "camcap.hash")
    if os.path.exists(hash_path):
        os.remove(hash_path)

    print(f"[INFO] Factory reset complete. Removed {removed} files.")
    print("[INFO] Next launch will prompt for new PIN setup.")


IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".bmp")


def encrypt_unprotected_images(folder_path: str, key: bytes) -> int:
    if not os.path.isdir(folder_path):
        return 0
    count = 0
    for fname in os.listdir(folder_path):
        if not fname.lower().endswith(IMAGE_EXTS):
            continue
        fpath = os.path.join(folder_path, fname)
        enc_path = fpath + ".enc"
        if os.path.exists(enc_path):
            continue
        try:
            encrypt_file(fpath, key, enc_path, delete_original=True)
            count += 1
        except Exception as e:
            print(f"[WARNING] Failed to encrypt {fname}: {e}")
    if count > 0:
        print(f"[INFO] Encrypted {count} unprotected image(s) in "
              f"{os.path.basename(folder_path)}/")
    return count


def get_session_key() -> bytes:
    # check the launcher already set the key
    hex_key = os.environ.get(ENV_KEY_NAME)
    if hex_key:
        return bytes.fromhex(hex_key)

    if not pin_exists():
        print("[ERROR] No PIN configured. Run launcher.py first to set up.")
        sys.exit(1)

    for attempt in range(MAX_ATTEMPTS):
        pin = getpass.getpass(
            f"Enter 4-digit PIN ({attempt+1}/{MAX_ATTEMPTS}): ")
        valid, key = verify_pin(pin)
        if valid:
            return key
        remaining = MAX_ATTEMPTS - attempt - 1
        if remaining > 0:
            print(f"[ERROR] Wrong PIN. {remaining} attempt(s) left.")
        else:
            print(f"[ERROR] {LOCKOUT_MSG}")
            sys.exit(1)

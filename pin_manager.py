#!/usr/bin/env python3

import argparse
import getpass
import sys
import os

from crypto_utils import (
    pin_exists, setup_pin, verify_pin, change_pin, factory_reset
)
from hailo_utils import ENCODINGS_DIR, FACEDATA_DIR


def _get_enc_dirs():
    return [
        ENCODINGS_DIR,
        os.path.join(FACEDATA_DIR, "camcap"),
    ]


def cmd_status():
    if pin_exists():
        print("PIN is configured.")
    else:
        print("No PIN configured. Run: python pin_manager.py --setup")


def cmd_setup():
    if pin_exists():
        print("PIN already exists. Use --change to change it, "
              "or --factory-reset to start fresh.")
        return

    print("First-Time PIN Setup")
    pin = getpass.getpass("Enter new 4-digit PIN: ")
    if len(pin) != 4 or not pin.isdigit():
        print("[ERROR] PIN must be exactly 4 digits.")
        return

    confirm = getpass.getpass("Confirm PIN: ")
    if pin != confirm:
        print("[ERROR] PINs do not match.")
        return

    setup_pin(pin)
    print("[OK] PIN created successfully.")


def cmd_change():
    if not pin_exists():
        print("No PIN configured yet. Use --setup first.")
        return

    print("Change PIN")
    old_pin = getpass.getpass("Enter current PIN: ")
    new_pin = getpass.getpass("Enter new 4-digit PIN: ")

    if len(new_pin) != 4 or not new_pin.isdigit():
        print("[ERROR] New PIN must be exactly 4 digits.")
        return

    confirm = getpass.getpass("Confirm new PIN: ")
    if new_pin != confirm:
        print("[ERROR] New PINs do not match.")
        return

    success, result = change_pin(old_pin, new_pin, _get_enc_dirs())
    if success:
        print("[OK] PIN changed successfully.")
    else:
        print(f"[ERROR] {result}")


def cmd_factory_reset():
    if not pin_exists():
        print("No PIN configured. Nothing to reset.")
        return

    print("=" * 50)
    print("  WARNING: FACTORY RESET")
    print("=" * 50)
    print()
    print("This will permanently delete:")
    print("Your encryption PIN")
    print("ALL encrypted camcap images")
    print("ALL encrypted face embeddings (pickle files)")
    print()
    print("You will need to:")
    print("Set up a new PIN")
    print("Recapture faces with image_capture.py")
    print("Re-enroll all face data")
    print()

    confirm = input("Type 'RESET' to confirm: ").strip()
    if confirm != "RESET":
        print("Cancelled.")
        return

    factory_reset()
    print("[OK] Factory reset complete.")


def main():
    ap = argparse.ArgumentParser()
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument("--status", action="store_true")
    group.add_argument("--setup", action="store_true")
    group.add_argument("--change", action="store_true")
    group.add_argument("--factory-reset", action="store_true")
    args = ap.parse_args()

    if args.status:
        cmd_status()
    elif args.setup:
        cmd_setup()
    elif args.change:
        cmd_change()
    elif args.factory_reset:
        cmd_factory_reset()


if __name__ == "__main__":
    main()

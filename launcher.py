#!/usr/bin/env python3

import os
import sys
import subprocess
import threading
import tkinter as tk
from tkinter import messagebox, filedialog
from datetime import datetime

from crypto_utils import (
    pin_exists, setup_pin, verify_pin, change_pin,
    factory_reset, encrypt_data_to_file, ENV_KEY_NAME, MAX_ATTEMPTS
)
from hailo_utils import ENCODINGS_DIR, FACEDATA_DIR

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

SCRIPTS = {
    "capture":   os.path.join(SCRIPT_DIR, "image_capture.py"),
    "enroll":    os.path.join(SCRIPT_DIR, "hailo_enroll.py"),
    "blur_all":  os.path.join(SCRIPT_DIR, "hailo_face_blur_all.py"),
    "blur_owners": os.path.join(SCRIPT_DIR, "hailo_face_blur_owners.py"),
    "blur_guests": os.path.join(SCRIPT_DIR, "hailo_face_blur_guests.py"),
}

# colors
BG           = "#1a1a2e"
BG_CARD      = "#16213e"
ACCENT       = "#0f3460"
ACCENT_HOVER = "#533483"
TEXT_PRIMARY  = "#e0e0e0"
TEXT_MUTED    = "#8892a0"
RED           = "#e74c3c"
GREEN         = "#2ecc71"
BLUE          = "#3498db"
ORANGE        = "#e67e22"
YELLOW        = "#f1c40f"


class PinDialog:
    def __init__(self, root, is_setup=False):
        self.root = root
        self.result_key = None
        self.is_setup = is_setup
        self.attempts = 0
        self.waiting = True

        self.container = tk.Frame(root, bg=BG)
        self.container.place(relx=0.5, rely=0.5, anchor="center")
        self._build_ui()

    def _build_ui(self):
        frame = tk.Frame(self.container, bg=BG)
        frame.pack(padx=40, pady=30)

        title = "Create 4-Digit PIN" if self.is_setup else "🔒 Enter PIN"
        tk.Label(frame, text=title, font=("Helvetica", 18, "bold"),
                 fg=TEXT_PRIMARY, bg=BG).pack(pady=(0, 5))

        if self.is_setup:
            tk.Label(frame, text="This PIN encrypts your face data.",
                     font=("Helvetica", 10), fg=TEXT_MUTED, bg=BG
                     ).pack(pady=(0, 15))

        tk.Label(frame, text="PIN:", font=("Helvetica", 11),
                 fg=TEXT_MUTED, bg=BG, anchor="w").pack(fill="x")
        self.pin_entry = tk.Entry(frame, show="*", font=("Helvetica", 22),
                                  justify="center", bg="#0d1117", fg=TEXT_PRIMARY,
                                  insertbackground=TEXT_PRIMARY, relief="flat",
                                  highlightthickness=1, highlightbackground=ACCENT,
                                  width=12)
        self.pin_entry.pack(fill="x", pady=(2, 10), ipady=6)
        self.pin_entry.focus_set()

        if self.is_setup:
            tk.Label(frame, text="Confirm PIN:", font=("Helvetica", 11),
                     fg=TEXT_MUTED, bg=BG, anchor="w").pack(fill="x")
            self.confirm_entry = tk.Entry(frame, show="*", font=("Helvetica", 22),
                                          justify="center", bg="#0d1117",
                                          fg=TEXT_PRIMARY,
                                          insertbackground=TEXT_PRIMARY,
                                          relief="flat", highlightthickness=1,
                                          highlightbackground=ACCENT, width=12)
            self.confirm_entry.pack(fill="x", pady=(2, 10), ipady=6)

        self.status_var = tk.StringVar(value="")
        tk.Label(frame, textvariable=self.status_var,
                 font=("Helvetica", 10), fg=RED, bg=BG).pack(pady=(0, 5))

        btn_text = "Create PIN" if self.is_setup else "Unlock"
        tk.Button(frame, text=btn_text, font=("Helvetica", 12, "bold"),
                  fg="white", bg=GREEN, activebackground="#27ae60",
                  relief="flat", padx=20, pady=8,
                  command=self._submit).pack(fill="x")

        self.pin_entry.bind("<Return>", lambda e: self._submit())
        if self.is_setup:
            self.confirm_entry.bind("<Return>", lambda e: self._submit())

    def _submit(self):
        pin = self.pin_entry.get().strip()

        if len(pin) != 4 or not pin.isdigit():
            self.status_var.set("PIN must be exactly 4 digits")
            self.pin_entry.delete(0, "end")
            self.pin_entry.focus_set()
            return

        if self.is_setup:
            confirm = self.confirm_entry.get().strip()
            if pin != confirm:
                self.status_var.set("PINs do not match")
                self.confirm_entry.delete(0, "end")
                self.confirm_entry.focus_set()
                return
            try:
                self.result_key = setup_pin(pin)
                self._done()
            except Exception as e:
                self.status_var.set(f"Error: {e}")
        else:
            valid, key = verify_pin(pin)
            if valid:
                self.result_key = key
                self._done()
            else:
                self.attempts += 1
                remaining = MAX_ATTEMPTS - self.attempts
                if remaining > 0:
                    self.status_var.set(
                        f"Wrong PIN. {remaining} attempt(s) left.")
                    self.pin_entry.delete(0, "end")
                    self.pin_entry.focus_set()
                else:
                    self.status_var.set("Too many attempts. Exiting.")
                    self.root.after(2000, self._close)

    def _done(self):
        self.waiting = False
        self.container.destroy()

    def _close(self):
        self.result_key = None
        self.waiting = False
        self.container.destroy()

    def wait(self):
        while self.waiting:
            self.root.update()
            self.root.after(50)
        return self.result_key


class ChangePinDialog:
    def __init__(self, root):
        self.root = root
        self.success = False
        self.new_key = None
        self.waiting = True

        self.overlay = tk.Frame(root, bg=BG)
        self.overlay.place(relx=0, rely=0, relwidth=1, relheight=1)

        self.container = tk.Frame(self.overlay, bg=BG_CARD,
                                  highlightthickness=2,
                                  highlightbackground=ACCENT)
        self.container.place(relx=0.5, rely=0.5, anchor="center")

        self._build_ui()

    def _build_ui(self):
        frame = tk.Frame(self.container, bg=BG_CARD)
        frame.pack(padx=30, pady=25)

        tk.Label(frame, text="Change PIN", font=("Helvetica", 16, "bold"),
                 fg=TEXT_PRIMARY, bg=BG_CARD).pack(pady=(0, 15))

        tk.Label(frame, text="Current PIN:", font=("Helvetica", 11),
                 fg=TEXT_MUTED, bg=BG_CARD, anchor="w").pack(fill="x")
        self.old_entry = tk.Entry(frame, show="*", font=("Helvetica", 18),
                                  justify="center", bg="#0d1117", fg=TEXT_PRIMARY,
                                  insertbackground=TEXT_PRIMARY, relief="flat",
                                  highlightthickness=1, highlightbackground=ACCENT,
                                  width=12)
        self.old_entry.pack(fill="x", pady=(2, 8), ipady=4)
        self.old_entry.focus_set()

        tk.Label(frame, text="New PIN:", font=("Helvetica", 11),
                 fg=TEXT_MUTED, bg=BG_CARD, anchor="w").pack(fill="x")
        self.new_entry = tk.Entry(frame, show="*", font=("Helvetica", 18),
                                  justify="center", bg="#0d1117", fg=TEXT_PRIMARY,
                                  insertbackground=TEXT_PRIMARY, relief="flat",
                                  highlightthickness=1, highlightbackground=ACCENT,
                                  width=12)
        self.new_entry.pack(fill="x", pady=(2, 8), ipady=4)

        tk.Label(frame, text="Confirm New PIN:", font=("Helvetica", 11),
                 fg=TEXT_MUTED, bg=BG_CARD, anchor="w").pack(fill="x")
        self.confirm_entry = tk.Entry(frame, show="*", font=("Helvetica", 18),
                                      justify="center", bg="#0d1117",
                                      fg=TEXT_PRIMARY,
                                      insertbackground=TEXT_PRIMARY, relief="flat",
                                      highlightthickness=1,
                                      highlightbackground=ACCENT, width=12)
        self.confirm_entry.pack(fill="x", pady=(2, 8), ipady=4)

        self.status_var = tk.StringVar(value="")
        tk.Label(frame, textvariable=self.status_var, font=("Helvetica", 10),
                 fg=RED, bg=BG_CARD).pack(pady=(0, 5))

        btn_row = tk.Frame(frame, bg=BG_CARD)
        btn_row.pack(fill="x", pady=(5, 0))

        tk.Button(btn_row, text="Cancel", font=("Helvetica", 11),
                  fg=TEXT_MUTED, bg=ACCENT, activebackground=ACCENT_HOVER,
                  relief="flat", padx=15, pady=6,
                  command=self._cancel).pack(side="left", expand=True, fill="x",
                                             padx=(0, 5))
        tk.Button(btn_row, text="Change PIN", font=("Helvetica", 11, "bold"),
                  fg="white", bg=ORANGE, activebackground="#d35400",
                  relief="flat", padx=15, pady=6,
                  command=self._submit).pack(side="right", expand=True, fill="x",
                                             padx=(5, 0))

        self.confirm_entry.bind("<Return>", lambda e: self._submit())

    def _submit(self):
        old = self.old_entry.get().strip()
        new = self.new_entry.get().strip()
        confirm = self.confirm_entry.get().strip()

        if len(new) != 4 or not new.isdigit():
            self.status_var.set("New PIN must be 4 digits")
            return
        if new != confirm:
            self.status_var.set("New PINs do not match")
            return

        enc_dirs = [ENCODINGS_DIR, os.path.join(FACEDATA_DIR, "camcap")]
        ok, result = change_pin(old, new, enc_dirs)

        if ok:
            self.success = True
            self.new_key = result
            self.waiting = False
            self.overlay.destroy()
        else:
            self.status_var.set(str(result))

    def _cancel(self):
        self.waiting = False
        self.overlay.destroy()

    def run(self):
        while self.waiting:
            self.root.update()
            self.root.after(50)
        return self.success, self.new_key


class FaceLauncher:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Privacy-Preserving Home Security Camera System")
        self.root.configure(bg=BG)
        self.root.resizable(True, True)

        try:
            sw = self.root.winfo_screenwidth()
            if sw <= 1024:
                self.root.attributes("-fullscreen", True)
            else:
                self.root.geometry("820x880")
        except Exception:
            self.root.geometry("820x880")

        self.session_key = None
        self.running_process = None
        self.status_var = tk.StringVar(value="Ready")
        self.log_text = None

        if not self._authenticate():
            self.root.destroy()
            sys.exit(0)

        self._build_ui()
        self.root.bind("<Escape>", self._on_escape)

    def _authenticate(self):
        is_setup = not pin_exists()
        dlg = PinDialog(self.root, is_setup=is_setup)
        key = dlg.wait()

        if key is None:
            return False

        self.session_key = key
        os.environ[ENV_KEY_NAME] = key.hex()
        return True

    def _build_ui(self):
        # title
        title_frame = tk.Frame(self.root, bg=BG)
        title_frame.pack(fill="x", padx=20, pady=(20, 5))
        tk.Label(title_frame, text="🔒  Privacy-Preserving Home Security Camera System",
                 font=("Helvetica", 22, "bold"), fg=TEXT_PRIMARY, bg=BG
                 ).pack(anchor="w")
        tk.Label(title_frame,
                 text="Hailo-10H Accelerated  /  AES-256 Encrypted  /  GDPR Compliant",
                 font=("Helvetica", 11), fg=TEXT_MUTED, bg=BG).pack(anchor="w")

        tk.Frame(self.root, bg=ACCENT, height=2).pack(fill="x", padx=20, pady=10)

        # buttons
        btn_frame = tk.Frame(self.root, bg=BG)
        btn_frame.pack(fill="x", padx=20, pady=5)

        self._make_button(btn_frame, "📷", "Register Faces",
                          "Capture with camera",
                          BLUE, self._run_capture, row=0, col=0)
        self._make_button(btn_frame, "📁", "Upload Faces",
                          "Browse image files",
                          "#9b59b6", self._upload_faces, row=0, col=1)
        self._make_button(btn_frame, "🧠", "Enroll Faces",
                          "Manual re-enroll (blur scripts auto-enroll)",
                          ORANGE, self._run_enroll, row=1, colspan=2)

        tk.Frame(btn_frame, bg=ACCENT, height=1).grid(
            row=2, column=0, columnspan=2, sticky="ew", padx=10, pady=8)

        self._make_button(btn_frame, "🔲", "Blur All Faces",
                          "Detect + blur every face / Auto-enrolls if needed",
                          RED, self._run_blur_all, row=3, colspan=2)
        self._make_button(btn_frame, "🏠", "Blur Owners",
                          "Blur enrolled owner faces / Auto-enrolls",
                          GREEN, self._run_blur_owners, row=4, col=0)
        self._make_button(btn_frame, "👤", "Blur Guests",
                          "Blur non-enrolled guest faces / Auto-enrolls",
                          BLUE, self._run_blur_guests, row=4, col=1)

        tk.Frame(btn_frame, bg=ACCENT, height=1).grid(
            row=5, column=0, columnspan=2, sticky="ew", padx=10, pady=8)

        self._make_button(btn_frame, "", "Change PIN",
                          "Change your 4-digit encryption PIN",
                          YELLOW, self._change_pin, row=6, colspan=2)

        btn_frame.columnconfigure(0, weight=1)
        btn_frame.columnconfigure(1, weight=1)

        # status bar
        status_frame = tk.Frame(self.root, bg=BG_CARD)
        status_frame.pack(fill="x", padx=20, pady=(10, 5))
        self.status_label = tk.Label(
            status_frame, textvariable=self.status_var,
            font=("Helvetica", 11), fg=YELLOW, bg=BG_CARD,
            anchor="w", padx=10, pady=5)
        self.status_label.pack(fill="x")

        # log
        log_frame = tk.Frame(self.root, bg=BG)
        log_frame.pack(fill="both", expand=True, padx=20, pady=(5, 10))
        tk.Label(log_frame, text="Output Log", font=("Helvetica", 10, "bold"),
                 fg=TEXT_MUTED, bg=BG, anchor="w").pack(fill="x")
        self.log_text = tk.Text(
            log_frame, height=10, font=("Courier", 10),
            fg=TEXT_PRIMARY, bg="#0d1117", insertbackground=TEXT_PRIMARY,
            relief="flat", highlightthickness=1, highlightbackground=ACCENT,
            wrap="word")
        self.log_text.pack(fill="both", expand=True, pady=(3, 0))
        scrollbar = tk.Scrollbar(self.log_text, command=self.log_text.yview)
        scrollbar.pack(side="right", fill="y")
        self.log_text.configure(yscrollcommand=scrollbar.set)

        # bottom bar
        bottom = tk.Frame(self.root, bg=BG)
        bottom.pack(fill="x", padx=20, pady=(0, 15))
        self.stop_btn = tk.Button(
            bottom, text="  Stop Task", font=("Helvetica", 11, "bold"),
            fg="white", bg=RED, activebackground="#c0392b",
            relief="flat", padx=20, pady=8,
            command=self._stop_process, state="disabled")
        self.stop_btn.pack(side="left")
        tk.Button(bottom, text="✕  Quit", font=("Helvetica", 11),
                  fg=TEXT_MUTED, bg=ACCENT, activebackground=ACCENT_HOVER,
                  relief="flat", padx=20, pady=8,
                  command=self._quit).pack(side="right")

    def _make_button(self, parent, icon, title, subtitle, color, command,
                     row, col=0, colspan=1):
        btn_frame = tk.Frame(parent, bg=BG_CARD, cursor="hand2",
                             highlightthickness=2, highlightbackground=ACCENT)
        btn_frame.grid(row=row, column=col, columnspan=colspan,
                       sticky="nsew", pady=4, padx=(0 if col == 0 else 4, 0))
        inner = tk.Frame(btn_frame, bg=BG_CARD)
        inner.pack(fill="x", padx=15, pady=10)
        icon_l = tk.Label(inner, text=icon, font=("Helvetica", 20),
                          fg=color, bg=BG_CARD)
        icon_l.pack(side="left", padx=(0, 12))
        text_f = tk.Frame(inner, bg=BG_CARD)
        text_f.pack(side="left", fill="x", expand=True)
        title_l = tk.Label(text_f, text=title, font=("Helvetica", 13, "bold"),
                           fg=TEXT_PRIMARY, bg=BG_CARD, anchor="w")
        title_l.pack(fill="x")
        sub_l = tk.Label(text_f, text=subtitle, font=("Helvetica", 10),
                         fg=TEXT_MUTED, bg=BG_CARD, anchor="w")
        sub_l.pack(fill="x")
        for w in [btn_frame, inner, icon_l, text_f, title_l, sub_l]:
            w.bind("<Button-1>", lambda e, cmd=command: cmd())
        def on_enter(e): btn_frame.configure(highlightbackground=color)
        def on_leave(e): btn_frame.configure(highlightbackground=ACCENT)
        btn_frame.bind("<Enter>", on_enter)
        btn_frame.bind("<Leave>", on_leave)

    def _log(self, msg):
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_text.insert("end", f"[{ts}] {msg}\n")
        self.log_text.see("end")

    def _clear_log(self):
        self.log_text.delete("1.0", "end")

    def _is_busy(self):
        if self.running_process and self.running_process.poll() is None:
            messagebox.showwarning("Task Running",
                                   "A task is already running. Stop it first.")
            return True
        return False

    def _run_script(self, script_key, label, extra_args=None, callback=None):
        path = SCRIPTS[script_key]
        if not os.path.exists(path):
            self._log(f"ERROR: Script not found: {path}")
            return
        self._clear_log()
        self.status_var.set(f"Running: {label}...")
        self.stop_btn.configure(state="normal")
        self._log(f"Starting {label}...")

        def run_thread():
            try:
                cmd = [sys.executable, path] + (extra_args or [])
                self.running_process = subprocess.Popen(
                    cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, bufsize=1, cwd=SCRIPT_DIR)
                for line in self.running_process.stdout:
                    self.root.after(0, self._log, line.rstrip())
                self.running_process.wait()
                rc = self.running_process.returncode
                self.running_process = None

                def finish():
                    self.stop_btn.configure(state="disabled")
                    if rc == 0:
                        self._log(f"\n{label} completed successfully.")
                        self.status_var.set(f"Done: {label}")
                        if callback:
                            callback()
                    else:
                        self._log(f"\n{label} exited with code {rc}")
                        self.status_var.set(f"Failed: {label} (code {rc})")
                self.root.after(0, finish)
            except Exception as e:
                self.root.after(0, self._log, f"ERROR: {e}")
                self.root.after(0, self.status_var.set, f"Error: {label}")
                self.root.after(0,
                                lambda: self.stop_btn.configure(state="disabled"))

        threading.Thread(target=run_thread, daemon=True).start()

    def _stop_process(self):
        if self.running_process and self.running_process.poll() is None:
            self._log("Stopping task...")
            self.running_process.terminate()
            try:
                self.running_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.running_process.kill()
            self.running_process = None
            self.status_var.set("Stopped")
            self.stop_btn.configure(state="disabled")
            self._log("Task stopped.")

    def _run_capture(self):
        if not self._is_busy():
            self._run_script("capture", "Register New Faces")

    def _upload_faces(self):
        filepaths = filedialog.askopenfilenames(
            title="Select Face Images",
            filetypes=[
                ("Image files", "*.jpg *.jpeg *.png *.bmp"),
                ("JPEG", "*.jpg *.jpeg"),
                ("PNG", "*.png"),
                ("BMP", "*.bmp"),
                ("All files", "*.*"),
            ]
        )
        if not filepaths:
            return

        camcap_dir = os.path.join(FACEDATA_DIR, "camcap")
        os.makedirs(camcap_dir, exist_ok=True)

        self._clear_log()
        self.status_var.set("Uploading faces...")
        count = 0

        for fpath in filepaths:
            fname = os.path.basename(fpath)
            enc_name = fname + ".enc"
            dest_path = os.path.join(camcap_dir, enc_name)

            if os.path.exists(dest_path):
                self._log(f"[SKIP] Already exists: {enc_name}")
                continue

            try:
                with open(fpath, "rb") as f:
                    raw_bytes = f.read()
                encrypt_data_to_file(raw_bytes, dest_path, self.session_key)
                count += 1
                self._log(f"[OK] Encrypted + saved: {enc_name}")
            except Exception as e:
                self._log(f"[ERROR] Failed: {fname}: {e}")

        if count > 0:
            self._log(f"\n{count} image(s) uploaded and encrypted.")
            self._log("Auto-enroll will pick these up on next blur run.")
            self.status_var.set(f"Uploaded {count} image(s)")
        else:
            self._log("No new images uploaded.")
            self.status_var.set("Ready")

    def _run_enroll(self):
        if not self._is_busy():
            self._run_script("enroll", "Enroll Faces")

    def _run_blur_all(self):
        if not self._is_busy():
            self._run_script("blur_all", "Blur All Faces")

    def _run_blur_owners(self):
        if not self._is_busy():
            self._run_script("blur_owners", "Blur Owners Only")

    def _run_blur_guests(self):
        if not self._is_busy():
            self._run_script("blur_guests", "Blur Guests Only")

    def _change_pin(self):
        if self._is_busy():
            return
        dlg = ChangePinDialog(self.root)
        success, new_key = dlg.run()
        if success and new_key is not None:
            self.session_key = new_key
            os.environ[ENV_KEY_NAME] = new_key.hex()
            self._log("PIN changed successfully. New key active.")
            self.status_var.set("PIN changed")

    def _on_escape(self, event=None):
        if self.root.attributes("-fullscreen"):
            self.root.attributes("-fullscreen", False)
            self.root.geometry("820x880")
        else:
            self._quit()

    def _quit(self):
        self._stop_process()
        os.environ.pop(ENV_KEY_NAME, None)
        self.root.destroy()

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    app = FaceLauncher()
    app.run()
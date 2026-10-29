#!/usr/bin/env python3
"""MailMend desktop shell (tkinter).
Pick an .mbox file -> cleaned .mbox + dedupe & repair report."""
import os
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from mail_mend import run_mailmend


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("MailMend — MBOX Dedupe & Repair")
        self.geometry("680x520")
        self.src = tk.StringVar()
        tk.Label(self, text="Mailbox file (.mbox — Thunderbird, Apple Mail, Google Takeout exports):").pack(anchor="w", padx=12, pady=(12, 2))
        row = tk.Frame(self)
        row.pack(fill="x", padx=12)
        tk.Entry(row, textvariable=self.src).pack(side="left", fill="x", expand=True)
        tk.Button(row, text="Browse…", command=self.pick).pack(side="left", padx=6)
        self.btn = tk.Button(self, text="Dedupe, Repair & Re-Check", command=self.run, height=2)
        self.btn.pack(pady=12)
        self.log = scrolledtext.ScrolledText(self, wrap="word")
        self.log.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        self.write("MailMend removes duplicate messages from an .mbox archive (by Message-ID,\n"
                   "or by content for mail that has none), repairs messages split apart by an\n"
                   "unescaped 'From ' line in the body, then re-parses the cleaned file to prove\n"
                   "zero duplicates remain. Your original file is never modified.\n")

    def write(self, s):
        self.log.insert("end", s)
        self.log.see("end")

    def pick(self):
        p = filedialog.askopenfilename(filetypes=[("Mailbox files", "*.mbox *.mbx"), ("All files", "*.*")])
        if p:
            self.src.set(p)

    def run(self):
        src = self.src.get().strip()
        if not src or not os.path.isfile(src):
            messagebox.showerror("MailMend", "Choose an .mbox file first.")
            return
        self.btn.config(state="disabled")
        threading.Thread(target=self._work, args=(src,), daemon=True).start()

    def _work(self, src):
        try:
            outdir = os.path.join(os.path.dirname(os.path.abspath(src)), "mailmend_output")
            s = run_mailmend(src, outdir)
            self.write(f"\nDone. {s['found']} messages found, {s['kept']} kept, "
                       f"{s['removed']} duplicates removed, {s['fragments']} split message(s) rejoined.\n"
                       f"Re-check: {'PASS' if s['recheck_ok'] else 'FAIL'} "
                       f"(conservation {'holds' if s['conservation'] else 'BROKEN'})\n"
                       f"Cleaned mailbox: {s['out_path']}\nReport: {s['report_path']}\n")
        except Exception as e:
            self.write(f"\nError: {e}\n")
        finally:
            self.btn.config(state="normal")


if __name__ == "__main__":
    App().mainloop()

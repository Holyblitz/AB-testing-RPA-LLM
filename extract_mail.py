# fetch_imap_trash.py
# Usage:
#   IMAP_HOST=imap.gmail.com IMAP_USER="you@example.com" IMAP_PASS="app_password" python3 fetch_imap_trash.py 50
# Notes:
# - Pour Gmail: crée un "App password" (2FA requis). Boîte corbeille = "[Gmail]/Trash".
# - Pour autres providers: ajuste IMAP_HOST et MAILBOX_CANDIDATES.
import os, imaplib, email, re, sys, unicodedata
from pathlib import Path
from email.header import decode_header, make_header

SAVE_DIR = Path("data/emails")
SAVE_DIR.mkdir(parents=True, exist_ok=True)

IMAP_HOST = os.getenv("IMAP_HOST", "imap.gmail.com")
IMAP_USER = os.getenv("IMAP_USER")
IMAP_PASS = os.getenv("IMAP_PASS")
MAILBOX_CANDIDATES = ["[Gmail]/Trash", "Trash", "Corbeille", "Deleted Items", "INBOX.Trash"]

LABELS = ["invoice","job","support","sales","newsletter","spam","other"]  # pour naming futur

def norm_filename(s: str) -> str:
    s = "".join(c for c in unicodedata.normalize("NFKD", s) if ord(c) < 128)
    s = re.sub(r"[^\w\-]+", "_", s).strip("_")
    return s or "no_subject"

def body_to_text(msg):
    parts = []
    if msg.is_multipart():
        for part in msg.walk():
            ctype = part.get_content_type()
            disp = str(part.get("Content-Disposition", "")).lower()
            if "attachment" in disp:
                continue
            if ctype in ("text/plain", "text/html"):
                try:
                    payload = part.get_payload(decode=True) or b""
                    txt = payload.decode(part.get_content_charset() or "utf-8", errors="ignore")
                    if ctype == "text/html":
                        # enlever HTML vite fait
                        txt = re.sub(r"<br\s*/?>", "\n", txt, flags=re.I)
                        txt = re.sub(r"<[^>]+>", " ", txt)
                    parts.append(txt)
                except Exception:
                    pass
    else:
        payload = msg.get_payload(decode=True) or b""
        txt = payload.decode(msg.get_content_charset() or "utf-8", errors="ignore")
        parts.append(txt)
    text = "\n".join(parts)
    # anonymisation légère
    text = re.sub(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", "<EMAIL>", text)
    text = re.sub(r"\b(?:\+?\d[\d \-().]{6,}\d)\b", "<PHONE>", text)
    return text

def main():
    nmax = int(sys.argv[1]) if len(sys.argv) > 1 else 50
    assert IMAP_USER and IMAP_PASS, "Set IMAP_USER and IMAP_PASS env vars."
    M = imaplib.IMAP4_SSL(IMAP_HOST)
    M.login(IMAP_USER, IMAP_PASS)

    # trouver une corbeille dispo
    mailbox = None
    for mb in MAILBOX_CANDIDATES:
        try:
            rv, _ = M.select(f'"{mb}"', readonly=True)
            if rv == "OK":
                mailbox = mb
                break
        except Exception:
            continue
    if not mailbox:
        raise RuntimeError("Trash mailbox not found. Try setting MAILBOX_CANDIDATES.")

    rv, data = M.search(None, "ALL")
    ids = data[0].split()
    ids = ids[-nmax:]  # derniers n emails
    print(f"Fetching {len(ids)} from {mailbox} on {IMAP_HOST}...")

    for i, msg_id in enumerate(ids, 1):
        rv, msgdata = M.fetch(msg_id, "(RFC822)")
        if rv != "OK": continue
        msg = email.message_from_bytes(msgdata[0][1])
        subj = str(make_header(decode_header(msg.get("Subject","(no subject)"))))
        frm  = str(make_header(decode_header(msg.get("From",""))))
        date = msg.get("Date","")
        text = body_to_text(msg)
        content = f"Subject: {subj}\nFrom: {frm}\nDate: {date}\n\n{text}".strip()

        base = norm_filename(subj)[:60]
        # par défaut label "other" — tu ajusteras via la CLI labeling
        fname = f"other__{i:03d}__{base}.txt"
        (SAVE_DIR / fname).write_text(content, encoding="utf-8")
        print(f"[{i}/{len(ids)}] -> {fname}")

    M.close(); M.logout()
    print(f"✅ Saved {len(ids)} emails to {SAVE_DIR}")

if __name__ == "__main__":
    main()


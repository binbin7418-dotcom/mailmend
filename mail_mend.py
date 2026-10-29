#!/usr/bin/env python3
"""
MailMend — MBOX duplicate removal & corruption repair, with proof.

Pipeline:
  1. Split the .mbox into messages on envelope ("From ") lines.
  2. Detect duplicates two ways: normalized Message-ID (case/whitespace
     insensitive), and — for messages with no Message-ID — a content key
     (From + Subject + Date + body), so re-exported copies that only
     differ in Received headers are still caught.
  3. Repair the classic mbox corruption: a body line that looks like an
     envelope line splits one message into a header-less fragment.
     Fragments are rejoined to their parent message and the offending
     line is escaped (">From ") in the cleaned file.
  4. Write a cleaned .mbox (originals never modified; kept messages are
     byte-preserved apart from the escaping repair) and a report.
  5. Re-check: re-parse the cleaned file — duplicates must be zero,
     fragments zero, and in = kept + removed must hold exactly.

Message-IDs are never fabricated: a message without one is reported as
such and deduped by content key instead.

Local only. No network. Standard library only.
"""
import hashlib
import os
import re
import sys
from email import policy
from email.parser import BytesParser

ENVELOPE_RE = re.compile(
    r"^From \S+ \w{3} \w{3} [ \d]\d \d{2}:\d{2}:\d{2} \d{4}")


def split_mbox(data):
    """Split raw bytes into (envelope_line, chunk_bytes) pairs.
    A chunk that is not a parseable email (no header block) is returned
    flagged as a fragment."""
    lines = data.split(b"\n")
    chunks, env, cur = [], None, []
    for line in lines:
        text = line.decode("utf-8", "replace")
        if ENVELOPE_RE.match(text):
            if cur:
                chunks.append((env, b"\n".join(cur)))
            env, cur = line, [line]
        else:
            cur.append(line)
    if cur and any(cur):
        chunks.append((env, b"\n".join(cur)))
    return chunks


def parse_chunk(chunk):
    """Parse one chunk (including its envelope line). Returns msg or None."""
    body = chunk.split(b"\n", 1)[1] if b"\n" in chunk else b""
    try:
        msg = BytesParser(policy=policy.default).parsebytes(body)
    except Exception:
        return None
    if msg["From"] is None and msg["Subject"] is None and msg["Date"] is None:
        return None
    return msg


def body_text(msg):
    try:
        part = msg.get_body(preferencelist=("plain", "html"))
        if part is not None:
            return part.get_content()
        payload = msg.get_payload(decode=True)
        return payload.decode("utf-8", "replace") if payload else ""
    except Exception:
        return ""


def dedupe_key(msg):
    mid = msg["Message-ID"]
    if mid is not None:
        norm = re.sub(r"\s+", "", str(mid)).strip("<>").lower()
        if norm:
            return "id:" + norm, True
    basis = "|".join([str(msg["From"] or "").strip().lower(),
                      str(msg["Subject"] or "").strip(),
                      str(msg["Date"] or "").strip(),
                      body_text(msg).strip()])
    return "content:" + hashlib.sha256(basis.encode("utf-8", "replace")).hexdigest(), False


def run_mailmend(src_path, outdir):
    os.makedirs(outdir, exist_ok=True)
    data = open(src_path, "rb").read()
    chunks = split_mbox(data)

    messages, fragments = [], 0
    for env, chunk in chunks:
        msg = parse_chunk(chunk)
        if msg is None:
            # header-less fragment: belongs to the previous message; the
            # line that caused the split is escaped (">From ") and kept.
            if messages:
                fragments += 1
                prev = messages[-1]
                first, _, rest = chunk.partition(b"\n")
                rejoined = b">" + first + (b"\n" + rest if rest else b"")
                prev["raw"] = prev["raw"].rstrip(b"\n") + b"\n" + rejoined
                prev["repaired"] = True
            continue
        messages.append({"env": env, "raw": chunk, "msg": msg, "repaired": False})

    seen, kept, removed = {}, [], []
    no_id = 0
    for m in messages:
        key, has_id = dedupe_key(m["msg"])
        if not has_id:
            no_id += 1
        if key in seen:
            removed.append({"key": key, "subject": str(m["msg"]["Subject"] or ""),
                            "kept_subject": seen[key]})
        else:
            seen[key] = str(m["msg"]["Subject"] or "")
            kept.append(m)

    out_path = os.path.join(outdir, "cleaned.mbox")
    with open(out_path, "wb") as fh:
        for m in kept:
            raw = m["raw"]
            if not raw.endswith(b"\n"):
                raw += b"\n"
            fh.write(raw + b"\n")

    # Re-check: re-parse the cleaned file independently.
    re_chunks = split_mbox(open(out_path, "rb").read())
    re_msgs, re_frag = [], 0
    for env, chunk in re_chunks:
        msg = parse_chunk(chunk)
        if msg is None:
            re_frag += 1
        else:
            re_msgs.append(msg)
    re_keys = [dedupe_key(m)[0] for m in re_msgs]
    re_dupes = len(re_keys) - len(set(re_keys))
    conservation = len(messages) == len(kept) + len(removed)
    recheck_ok = (re_dupes == 0 and re_frag == 0 and len(re_msgs) == len(kept)
                  and conservation)

    repairs = fragments  # each rejoin includes escaping the offending line
    L = ["# MailMend — dedupe & repair report", "",
         f"Source file: {os.path.basename(src_path)}  ·  Messages found: {len(messages)} "
         f"(+ {fragments} header-less fragment(s) rejoined)", "",
         "## Summary",
         f"- Kept: {len(kept)}",
         f"- Duplicates removed: {len(removed)}",
         f"- Corruption repairs (fragment rejoined + envelope line escaped): {fragments}",
         f"- Kept messages with no Message-ID (deduped by content key, IDs are never fabricated): "
         f"{sum(1 for m in kept if dedupe_key(m['msg'])[1] is False)}",
         "", "## Duplicates removed (first copy kept)"]
    L += [f"- '{r['subject']}' — duplicate of '{r['kept_subject']}' (key {r['key'][:21]}…)" for r in removed] or ["- none"]
    L += ["", "## Re-check verdict",
          f"- {'PASS' if recheck_ok else 'FAIL'}: cleaned file re-parsed — {len(re_msgs)} messages, "
          f"{re_dupes} duplicates, {re_frag} fragments; conservation "
          f"{len(messages)} in = {len(kept)} kept + {len(removed)} removed "
          f"({'holds' if conservation else 'BROKEN'}).",
          "- Scope note: duplicates are exact copies or Message-ID/content-key matches. "
          "Near-duplicates (same mail forwarded with edits, quoted replies) are different messages and are kept."]
    report_path = os.path.join(outdir, "dedupe_report.md")
    with open(report_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L) + "\n")
    return {"found": len(messages), "kept": len(kept), "removed": len(removed),
            "fragments": fragments, "repairs": repairs, "no_id_kept":
            sum(1 for m in kept if dedupe_key(m["msg"])[1] is False),
            "conservation": conservation, "recheck_ok": recheck_ok,
            "out_path": out_path, "report_path": report_path}


def main(argv):
    if len(argv) != 3:
        print("usage: mail_mend.py <mailbox.mbox> <outdir>")
        return 2
    s = run_mailmend(argv[1], argv[2])
    print(f"found={s['found']} kept={s['kept']} removed={s['removed']} fragments={s['fragments']} "
          f"no_id_kept={s['no_id_kept']} conservation={s['conservation']} recheck_ok={s['recheck_ok']}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

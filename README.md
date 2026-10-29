# MailMend

Remove duplicate messages from an .mbox mailbox and repair split
messages — then prove it by re-parsing the cleaned file.

## What it does

- Input: `.mbox` archives (Thunderbird, Apple Mail, Google Takeout,
  any mbox export).
- Duplicates are caught two ways: normalized Message-ID (immune to
  case/whitespace differences), and a content key (From + Subject +
  Date + body) for messages that have no Message-ID — so a re-exported
  copy that only differs in its Received headers is still caught.
- Repairs the classic mbox corruption: a body line that looks like an
  envelope line splits a message in two. The header-less fragment is
  rejoined to its parent and the line is escaped (`>From `).
- Kept messages are byte-preserved (attachments untouched). The
  original file is never modified. Message-IDs are never fabricated.
- Re-check: the cleaned file is re-parsed independently — duplicates
  must be 0, fragments 0, and in = kept + removed must hold exactly.

100% local. No account, no upload, no subscription — your mail archive
is the most private file you own, and it stays on your computer.

## Run from source

```bash
python mail_mend.py sample_mailbox.mbox out/
python gui.py
```

## Acceptance

`test/acceptance_test.py` builds a seeded 8-message mbox (three kinds
of planted duplicates + one split message) and asserts the exact
kept/removed counts, content preservation and the re-check verdict.
See `test/ACCEPTANCE.md`.

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""mmrm_fidelity.py - that the note describes the program it claims to describe.

Two mechanical claims:

  1. The two SAS listings printed in section 3 of the note appear in
     mmrm_check.sas as a *contiguous* run of statements - comments, case and
     whitespace ignored, string literals preserved so 'Placebo' cannot drift
     into something else without failing.
  2. Every expected value the check asserts (its `want = '...'` column) is
     also stated in the note, so a number that drifts in the prose fails.

Exits non-zero if either claim breaks.
"""
import hashlib
import html
import io
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
NOTE = os.path.join(HERE, "..", "mmrm-clinical-note.html")
PROG = os.path.join(HERE, "..", "mmrm_check.sas")

fails = []


def read(p):
    with io.open(os.path.normpath(p), encoding="utf-8") as fh:
        return fh.read()


def strip_spans(s):
    return re.sub(r"</?span[^>]*>", "", s)


def note_blocks():
    """Every <pre><code> in the note, de-spanned and unescaped."""
    src = read(NOTE)
    out = []
    for m in re.finditer(r"<pre><code>(.*?)</code></pre>", src, re.S):
        t = strip_spans(m.group(1))
        out.append(html.unescape(t))
    return out


def mask_literals(s):
    """Replace '...' with a placeholder keyed by a hash of its exact text.

    Keyed by content, not by position, so the same literal yields the same
    placeholder whether it is masked inside a two-statement listing or inside
    the whole program. Masking before the whitespace fold is what keeps ', '
    distinguishable from ','.
    """
    def rep(m):
        return "\x00%s\x00" % hashlib.md5(
            m.group(0).encode("utf-8")).hexdigest()[:8]

    return re.sub(r"'[^']*'", rep, s)


def statements(src):
    """Normalised statement list: comments gone, case folded, whitespace
    collapsed, string literals masked."""
    src = re.sub(r"/\*.*?\*/", " ", src, flags=re.S)
    src = mask_literals(src)
    out = []
    for st in src.split(";"):
        st = re.sub(r"\s+", " ", st).strip().lower()
        if st:
            out.append(st)
    return out


def main():
    note = note_blocks()
    prog = read(PROG)
    prog_st = statements(prog)

    # --- claim 1: the two program listings -------------------------------
    # identified by their leading statement, not by position
    wanted = {
        "3.1 analysis dataset": "data adbds",
        "3.2 main fit": "proc mixed data=adbds method=reml",
    }
    matched = 0
    for label, lead in wanted.items():
        cand = [b for b in note if statements(b) and statements(b)[0].startswith(lead)]
        if not cand:
            fails.append("note: no listing found for %s (lead %r)" % (label, lead))
            continue
        blk = statements(cand[0])
        # contiguous subsequence?
        first = blk[0]
        starts = [i for i, s in enumerate(prog_st) if s == first]
        hit = any(prog_st[i:i + len(blk)] == blk for i in starts)
        if hit:
            matched += 1
            print("ok   %-24s %2d statements, contiguous in mmrm_check.sas"
                  % (label, len(blk)))
        else:
            fails.append("%s: listing is not a contiguous run in the program"
                         % label)
            if not starts:
                fails.append("     leading statement never appears: %r" % first)

    if matched != len(wanted):
        fails.append("expected %d program listings, matched %d"
                     % (len(wanted), matched))

    # --- claim 2: every asserted value appears in the note ---------------
    # the `want = '..'; got = ..` pairs in the results step only - the PROC
    # PRINT label statement also reads `want = 'Expected'` and is not a claim.
    # YES / NO are flags about the fixture, not numbers the note must restate.
    wants = re.findall(r"want\s*=\s*'([^']*)'\s*;\s*got\s*=", prog)
    wants = sorted(set(w for w in wants if w not in ("YES", "NO")))
    note_text = read(NOTE)
    missing = []
    for w in wants:
        # as a table cell, a bold, or inside a <span class="num">
        pats = [r">\s*%s\s*<" % re.escape(w),
                r'<span class="num">[^<]*\b%s\b[^<]*</span>' % re.escape(w)]
        if not any(re.search(p, note_text) for p in pats):
            missing.append(w)
    if missing:
        fails.append("expected values asserted by the check but absent from "
                     "the note: %s" % ", ".join(missing))
    else:
        print("ok   %-24s all %d asserted values stated in the note"
              % ("asserted values", len(wants)))

    # --- report ----------------------------------------------------------
    print("")
    if fails:
        for f in fails:
            print("FAIL " + f)
        sys.exit(1)
    print("mmrm_fidelity: %d listings + %d values verified"
          % (matched, len(wants)))


main()

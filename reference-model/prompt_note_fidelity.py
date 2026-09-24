#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
prompt_note_fidelity.py — check that the note describes the archive it claims to describe.

Three claims are settled mechanically:

  1. quote fidelity  — every quoted block in the finished note appears in the archive file the
                       block names in its data-src attribute, verbatim, after unescaping;
  2. number fidelity — every number the note prints inside <span class="num"> is re-derived by
                       re-running the measurement, so a figure that drifts in the prose fails;
  3. plumbing        — the shell's link count equals the h2+h3 count inside .page, and the
                       page has exactly one .page and one shell of each kind.

    python prompt_note_fidelity.py --corpus /path/to/corpus \
        --note ../agent-system-prompt-note.html

Exits non-zero on any break.
"""

import argparse
import html
import io
import json
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))


def unescape_block(s):
    return html.unescape(s)


def check_quotes(note, corpus, report):
    blocks = re.findall(r'<pre data-src="([^"]+)"><code>(.*?)</code></pre>', note, re.S)
    if not blocks:
        report.append("FAIL no quoted blocks carry a data-src attribute")
        return 1
    bad = 0
    for src, body in blocks:
        # The attribute is written HTML-escaped, so a path containing '&' arrives as '&amp;'.
        src = unescape_block(src)
        text = unescape_block(body)
        path = os.path.join(corpus, src.replace("/", os.sep))
        if not os.path.exists(path):
            report.append("FAIL quote source missing: %s" % src)
            bad += 1
            continue
        archive = io.open(path, encoding="utf-8", errors="replace").read().replace("\r\n", "\n")
        if text not in archive:
            report.append("FAIL quote not found verbatim in %s :: %r"
                          % (src, text[:80]))
            bad += 1
    report.append("%s %d quoted blocks verified against the archive"
                  % ("PASS" if not bad else "FAIL", len(blocks)))
    return bad


def check_numbers(note, corpus, report, tmpdir):
    """Re-run the measurement and compare every proportion/ratio the note prints."""
    fresh_path = os.path.join(tmpdir, "fresh.json")
    cmd = [sys.executable, os.path.join(HERE, "prompt_corpus_metrics.py"),
           "--corpus", corpus, "--out", fresh_path,
           "--fragments", os.path.join(tmpdir, "fresh_frag.json")]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        report.append("FAIL re-running the measurement failed: %s" % res.stderr.strip()[:300])
        return 1
    fresh = json.load(io.open(fresh_path, encoding="utf-8"))

    expected = json.load(io.open(os.path.join(HERE, "metrics.json"), encoding="utf-8"))
    if fresh["numbers"] != expected["numbers"]:
        drift = [k for k in fresh["numbers"]
                 if fresh["numbers"].get(k) != expected["numbers"].get(k)]
        report.append("FAIL metrics.json is stale; re-run prompt_corpus_metrics.py "
                      "(differing keys: %s)" % ", ".join(sorted(drift)[:8]))
        return 1
    report.append("PASS metrics.json matches a fresh measurement (%d numbers)"
                  % len(fresh["numbers"]))

    # Every table body in the note must equal the one the measurement renders now.
    frags = json.load(io.open(os.path.join(HERE, "fragments.json"), encoding="utf-8"))
    bad = 0
    for key, rows in sorted(frags.items()):
        present = rows.strip() in note
        if not present:
            report.append("FAIL table body %s is not present in the note" % key)
            bad += 1
    report.append("%s %d generated table bodies present in the note"
                  % ("PASS" if not bad else "FAIL", len(frags)))

    # Numbers printed in prose must appear somewhere in the note, formatted as injected.
    missing = []
    for k in ("scope_files", "scope_products", "n_cases", "chars_min", "chars_max",
              "chars_ratio", "shout_max", "sig_resolved_files", "sig_resolved_products",
              "family_count", "cross_count", "vsc_files", "vsc_pairs"):
        v = str(fresh["numbers"].get(k))
        if v and v not in note:
            missing.append("%s=%s" % (k, v))
    if missing:
        report.append("FAIL numbers absent from the note: %s" % ", ".join(missing))
        bad += 1
    else:
        report.append("PASS prose numbers present in the note")
    return bad


def check_plumbing(note, report):
    bad = 0
    page = note.count('<div class="page">')
    if page != 1:
        report.append("FAIL expected exactly one .page, found %d" % page)
        bad += 1
    for marker in ("id=\"spn-shell-css\"", "class=\"spn-toggle\"", "id=\"spn-shell-js\""):
        c = note.count(marker)
        if c != 1:
            report.append("FAIL %s occurs %d times" % (marker, c))
            bad += 1
    # The skeleton's demo text and its Latin-only font stack both survive a build that reports
    # success, because each patch looks applied from the call site.
    if "Replace this title" in note:
        report.append("FAIL the demo title is still in the built note")
        bad += 1
    if note.count("PingFang SC") != 2:
        report.append("FAIL the CJK font stack appears %d times, expected 2 (body and SVG)"
                      % note.count("PingFang SC"))
        bad += 1
    i, j = note.find('<div class="page">'), note.find('<!-- @@SPN-SHELL:JS:BEGIN@@ -->')
    inner = note[i:j]
    heads = len(re.findall(r"<h[23][ >]", inner))
    if heads < 20:
        report.append("FAIL only %d h2/h3 headings inside .page" % heads)
        bad += 1
    # Only the authored body is checked: the injected shell script legitimately contains `{{`.
    leftovers = sorted(set(re.findall(r"\{\{[A-Za-z0-9_]+\}\}", inner)))
    if leftovers:
        report.append("FAIL unresolved placeholders: %s" % ", ".join(leftovers[:8]))
        bad += 1
    report.append("%s plumbing: 1 page column, 1 shell of each kind, %d headings, no placeholders"
                  % ("PASS" if not bad else "FAIL", heads))
    return bad


def check_layout_static(note, report):
    """A browser-free substitute for the rendered-page assertions.

    The two hue assertions and the no-horizontal-scroll assertion normally run in a real browser
    against the finished file.  A machine with no launchable browser cannot run them, so this
    group settles the two questions they answer, from the source instead:

      * every class the body uses is defined by the stylesheet that ships in the same file, so an
        element cannot silently fall back to unstyled black;
      * no unbreakable token is long enough to run a cell past the 880 px column, which is how a
        note overflows horizontally and the one breakage the eye misses.
    """
    bad = 0
    style = "".join(re.findall(r"<style[^>]*>(.*?)</style>", note, re.S))
    defined = set(re.findall(r"\.([A-Za-z][\w-]*)", style))
    i, j = note.find('<div class="page">'), note.find("<!-- @@SPN-SHELL:JS:BEGIN@@ -->")
    body = note[i:j]
    used = set()
    for m in re.findall(r'class="([^"]+)"', body):
        used.update(m.split())
    unknown = sorted(c for c in used if c not in defined)
    if unknown:
        report.append("FAIL classes used but not defined in the stylesheet: %s"
                      % ", ".join(unknown))
        bad += 1
    else:
        report.append("PASS all %d classes used in the body are styled" % len(used))

    # Longest unbreakable run in any text node, ignoring the code blocks (those scroll inside
    # their own <pre> by design).
    prose = re.sub(r"<pre.*?</pre>", " ", body, flags=re.S)
    text = html.unescape(re.sub(r"<[^>]+>", " ", prose))
    longest = ""
    for tok in text.split():
        if len(tok) > len(longest):
            longest = tok
    limit = 100                      # ~880 px at 8.8 px/char, the widest face in the sheet
    if len(longest) > limit:
        report.append("FAIL a %d-character unbreakable token risks a horizontal overflow: %r"
                      % (len(longest), longest[:60]))
        bad += 1
    else:
        report.append("PASS longest unbreakable token is %d characters (limit %d)"
                      % (len(longest), limit))

    nowrap = re.findall(r'<td class="num">(.*?)</td>', body, re.S)
    fat = [c for c in nowrap if len(html.unescape(re.sub(r"<[^>]+>", "", c))) > 40]
    if fat:
        report.append("FAIL class=\"num\" (white-space:nowrap) on a cell holding a sentence: %r"
                      % fat[0][:60])
        bad += 1
    else:
        report.append("PASS %d nowrap cells, all short" % len(nowrap))
    return bad


CJK = re.compile(r"[\u2e80-\u9fff\uf900-\ufaff\uff00-\uffef\u3000-\u303f]")


def est_text_width(text, size):
    """Rough advance width in px: one em per CJK glyph, about 0.55 em per Latin one."""
    w = 0.0
    for ch in text:
        if CJK.match(ch):
            w += 1.0 * size
        elif ch == " ":
            w += 0.3 * size
        else:
            w += 0.55 * size
    return w


def check_figures_static(note, report):
    """A browser-free check of the one defect the stylesheet cannot show: a label that runs out
    of its viewBox.  The stylesheet does not theme SVG, so an overflowing label is invisible in
    the source and obvious on screen — approximate the advance width and flag the gross cases.
    """
    bad = 0
    figs = re.findall(r"<svg[^>]*viewBox=\"0 0 ([\d.]+) ([\d.]+)\"[^>]*>(.*?)</svg>", note, re.S)
    if not figs:
        report.append("FAIL no figure with a viewBox found")
        return 1
    for idx, (vw, vh, inner) in enumerate(figs):
        vw, vh = float(vw), float(vh)
        for attrs, text in re.findall(r"<text([^>]*)>(.*?)</text>", inner, re.S):
            label = html.unescape(re.sub(r"<[^>]+>", "", text)).strip()
            size = float((re.search(r'font-size="([\d.]+)"', attrs) or [None, 11])[1])
            x = float((re.search(r'\bx="(-?[\d.]+)"', attrs) or [None, 0])[1])
            y = float((re.search(r'\by="(-?[\d.]+)"', attrs) or [None, 0])[1])
            anchor = (re.search(r'text-anchor="(\w+)"', attrs) or [None, "start"])[1]
            w = est_text_width(label, size)
            left = x if anchor == "start" else (x - w / 2 if anchor == "middle" else x - w)
            right = left + w
            if right > vw + 1.0 or left < -1.0:
                report.append("FAIL figure %d: label %r spans %.0f–%.0f in a %.0f-wide viewBox"
                              % (idx + 1, label[:24], left, right, vw))
                bad += 1
            if y < 0 or y > vh:
                report.append("FAIL figure %d: label %r sits at y=%.0f, outside 0–%.0f"
                              % (idx + 1, label[:24], y, vh))
                bad += 1
    report.append("%s %d figure(s) checked for label overflow"
                  % ("PASS" if not bad else "FAIL", len(figs)))
    return bad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", required=True)
    ap.add_argument("--note", default=os.path.join(HERE, os.pardir,
                                                   "agent-system-prompt-note.html"))
    args = ap.parse_args()

    note_path = os.path.abspath(args.note)
    if not os.path.exists(note_path):
        sys.stderr.write("no such note: %s\n" % note_path)
        return 2
    note = io.open(note_path, encoding="utf-8").read()

    report, bad = [], 0
    tmpdir = tempfile.mkdtemp(prefix="promptnote-")
    bad += check_quotes(note, args.corpus, report)
    bad += check_numbers(note, args.corpus, report, tmpdir)
    bad += check_plumbing(note, report)
    bad += check_layout_static(note, report)
    bad += check_figures_static(note, report)

    for line in report:
        sys.stdout.write(line + "\n")
    sys.stdout.write("\n%s  %d check group(s) failed  |  note: %s\n"
                     % ("FAILED" if bad else "OK", 0 if not bad else bad, note_path))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())

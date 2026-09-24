#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
prompt_notes_build.py — assemble agent-system-prompt-note.html.

Nothing in the note is retyped.  Three sources are spliced in:

  * every table body            <- fragments.json, written by prompt_corpus_metrics.py
  * every number in a sentence  <- the `numbers` block of metrics.json
  * every quoted prompt excerpt <- the archive itself, located by the anchors in quotes.json

so a figure that drifts out of the measurement has to be edited in two places to survive.

    python prompt_notes_build.py --corpus /path/to/corpus --out ../agent-system-prompt-note.html
"""

import argparse
import io
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.expanduser("~/.workbuddy/skills/sas-pattern-note")

TITLE = "SAS Pattern Note &mdash; Agent 系统提示词的设计模式：18 份真实发布稿的七个维度"
# Keys are lower_snake_case, so the character class has to accept lower case — an upper-case-only
# class silently matches nothing, the substitution becomes a no-op, and the build still reports
# success because nothing was left "unresolved".
PLACEHOLDER = re.compile(r"\{\{[A-Za-z0-9_]+\}\}")


def esc(text):
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def load_quotes(corpus):
    spec = json.load(io.open(os.path.join(HERE, "quotes.json"), encoding="utf-8"))
    blocks = {}
    problems = []
    for q in spec:
        path = os.path.join(corpus, q["src"].replace("/", os.sep))
        if not os.path.exists(path):
            problems.append("quote %s: no such file %s" % (q["id"], q["src"]))
            continue
        s = io.open(path, encoding="utf-8", errors="replace").read()
        i = s.find(q["start"])
        j = s.find(q["end"], i + len(q["start"])) if i >= 0 else -1
        if i < 0 or j < 0:
            problems.append("quote %s: anchor not found (start=%d end=%d)" % (q["id"], i, j))
            continue
        text = s[i:j + len(q["end"])].replace("\r\n", "\n").replace("\t", "    ").strip()
        if len(text) > q["cap"]:
            problems.append("quote %s: %d chars exceeds cap %d" % (q["id"], len(text), q["cap"]))
        blocks[q["id"]] = (
            '<pre data-src="{src}"><code>{body}</code></pre>\n'
            '<p class="small">取自 <code>{src}</code>，逐字切片</p>'
        ).format(src=esc(q["src"]), body=esc(text))
    return blocks, problems


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--title", default=TITLE)
    args = ap.parse_args()

    metrics = json.load(io.open(os.path.join(HERE, "metrics.json"), encoding="utf-8"))
    frags = json.load(io.open(os.path.join(HERE, "fragments.json"), encoding="utf-8"))
    body = io.open(os.path.join(HERE, "agent-system-prompt-note.body.html"), encoding="utf-8").read()

    values = dict(frags)
    values.update(metrics["numbers"])
    quotes, problems = load_quotes(args.corpus)
    values.update({"q_" + k: v for k, v in quotes.items()})
    if problems:
        for p in problems:
            sys.stderr.write("ERROR " + p + "\n")
        return 1

    remaining = set()
    def sub(m):
        key = m.group(0)[2:-2]
        if key in values:
            return str(values[key])
        remaining.add(key)
        return m.group(0)

    declared = body                      # pre-substitution, for the unused-direction check
    requested = PLACEHOLDER.findall(body)
    assert requested, "no placeholders found in the body — the pattern or the body is wrong"
    body = PLACEHOLDER.sub(sub, body)
    if remaining:
        sys.stderr.write("ERROR unresolved placeholders: %s\n" % ", ".join(sorted(remaining)))
        return 1
    # A quote that is extracted and never placed is evidence the note silently left out, so the
    # unused direction has to be checked as well — the substitution direction cannot see it.
    unused = sorted(set(quotes) - set(re.findall(r"\{\{q_([A-Za-z0-9_]+)\}\}", declared)))
    if unused:
        sys.stderr.write("ERROR quotes extracted but never used in the body: %s\n"
                         % ", ".join(unused))
        return 1
    unused_tables = sorted(set(frags) - set(re.findall(r"\{\{([A-Za-z0-9_]+)\}\}", declared)))
    if unused_tables:
        sys.stderr.write("ERROR table fragments rendered but never used: %s\n"
                         % ", ".join(unused_tables))
        return 1
    assert "{{" not in body, "a brace pair survived substitution"

    skel_path = os.path.join(SKILL, "assets", "note-skeleton.html")
    skel = io.open(skel_path, encoding="utf-8").read()

    # Each patch must take the string it returns and hand it on.  A helper that closes over the
    # pristine skeleton instead of the accumulating value asserts correctly on every call and
    # still discards all but the last patch, because every call starts from the original bytes.
    def once(s, old, new, label):
        assert s.count(old) == 1, "expected exactly one %s, found %d" % (label, s.count(old))
        return s.replace(old, new)

    s = once(skel, "<title>SAS Pattern Note — Replace this title</title>",
             "<title>%s</title>" % args.title, "placeholder title")
    s = once(s, "Helvetica,Arial,sans-serif;",
             'Helvetica,Arial,"PingFang SC","Microsoft YaHei",sans-serif;', "body font stack")
    s = once(s, "-apple-system,Segoe UI,Helvetica,Arial,sans-serif",
             "-apple-system,Segoe UI,'PingFang SC','Microsoft YaHei',Helvetica,Arial,sans-serif",
             "svg font stack")
    s = once(s, "font-size:15px; line-height:1.66;", "font-size:15px; line-height:1.75;",
             "body line height")

    # The patches above are the ones that fail silently: a missed title leaves the demo text in the
    # tab, and a missed font stack leaves every CJK glyph in a fallback face with different
    # metrics, which then reads as a geometry mistake elsewhere.  Check the result, not the calls.
    assert "Replace this title" not in s, "the demo title survived the patch"
    assert s.count("PingFang SC") == 2, \
        "the CJK font stack reached %d of the 2 stacks" % s.count("PingFang SC")
    assert s.count("line-height:1.75;") == 1, "the line-height patch did not apply"

    i = s.index('<div class="page">')
    j = s.index("<!-- @@SPN-SHELL:JS:BEGIN@@ -->")
    out = s[:i] + body.strip() + "\n\n" + s[j:]
    assert out.count("</body>") == 1 and out.count("</html>") == 1, "closing tags are not unique"
    assert out.count('<div class="page">') == 1, "the page column is not unique"

    io.open(args.out, "w", encoding="utf-8", newline="\n").write(out)
    sys.stdout.write("wrote %s (%d bytes, %d quotes, %d placeholders resolved)\n"
                     % (args.out, len(out.encode("utf-8")), len(quotes), len(requested)))
    return 0


if __name__ == "__main__":
    sys.exit(main())

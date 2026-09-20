# -*- coding: utf-8 -*-
"""Are the runs printed in the note still what the scripts print?

Sections 7.2, 7.3 and 7.4 of the note each quote a program's entire output. A
quoted run is only worth something if it is still quotable, so this re-runs all
three and compares them, byte for byte, with the blocks published in the note:

  7.2 dummy-data catalogue  <-  ec_chain_verify.py --cases
  7.3 the harness's report  <-  ec_chain_verify.py --json
  7.4 the fidelity check    <-  code_fidelity.py

Markup is stripped and entities are resolved before the comparison, so a
difference here is a difference in what the program printed, not in how the
note rendered it.

Any edit to a script, or to the note's section 7, invalidates this until it
passes again. Exit code is non-zero if any block has drifted.

Usage:
  python check_recorded_runs.py
  python check_recorded_runs.py --note path/to/index.html
"""
import argparse
import html as htmlmod
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)

# heading in the note -> the command whose output it is supposed to quote
RECORDED = [
    ("7.2 The dummy data, case by case", ("ec_chain_verify.py", "--cases")),
    ("7.3 The run, verbatim", ("ec_chain_verify.py", "--json")),
    ("7.4 The code-fidelity check", ("code_fidelity.py",)),
]


def read(p):
    s = open(p, encoding="utf-8", newline="").read()
    return s.replace("\r\n", "\n").replace("\r", "\n")


def block_after(note, heading, which=0):
    """The which-th <pre><code> block at or after a heading, as plain text."""
    at = note.find(heading)
    if at < 0:
        sys.exit("cannot find the heading %r in the note" % heading)
    blocks = re.findall(r"<pre><code>(.*?)</code></pre>", note[at:], re.S)
    if len(blocks) <= which:
        sys.exit("no code block after %r" % heading)
    return htmlmod.unescape(re.sub(r"<[^>]+>", "", blocks[which])).rstrip("\n")


def run(cmd):
    r = subprocess.run([sys.executable] + list(cmd), cwd=HERE,
                       capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0:
        sys.exit("%s exited %d:\n%s%s" % (cmd[0], r.returncode, r.stdout[-800:], r.stderr[-800:]))
    return r.stdout.replace("\r\n", "\n").rstrip("\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--note", default=os.path.join(REPO, "index.html"))
    args = ap.parse_args()

    note = read(args.note)
    fails = 0
    print("%-34s %-9s %-9s %s" % ("section", "in note", "re-run", ""))
    print("-" * 74)
    for heading, cmd in RECORDED:
        embedded = block_after(note, heading)
        fresh = run(cmd)
        same = embedded == fresh
        if not same:
            fails += 1
        print("%-34s %7d   %7d   %s" % (
            heading.split(" ", 1)[1][:34], embedded.count("\n") + 1,
            fresh.count("\n") + 1, "identical" if same else "DRIFTED"))
        if not same:
            import difflib
            for line in list(difflib.unified_diff(embedded.split("\n"), fresh.split("\n"),
                                                  "in the note", "re-run", lineterm=""))[:14]:
                print("    %s" % line)

    print("-" * 74)
    print("recorded runs: %s" % ("all live" if fails == 0 else "%d drifted" % fails))
    return 0 if fails == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

# -*- coding: utf-8 -*-
"""Does the code printed in the note actually equal the code in the program?

The note says its listings are the program, not a paraphrase of it. That is a
claim about two files, so it can be checked instead of trusted. This pairs

  note section 5.5, block 1, first half  <->  v_ec.sas 331-338   (split)
  note section 5.5, block 1, second half <->  v_ec.sas 344-346   (deduplicate)
  note section 5.5, block 2              <->  v_ec.sas 352-384   (walk)

and compares them statement by statement. Comparison is case-folded, with
comments and the note's own (12) markers removed and whitespace dropped around
operators, so comment numbering and indentation are free to differ and nothing
else is. String literals are masked before the whitespace pass: `|| ', ' ||`
and `||','||` are the same statement, `', '` and `','` are not, and a checker
that could not tell those apart would wave through a wrong separator.

It then works out what the hardening consists of, by diffing the note's
"before" listing (section 3) against the same ranges. The result must be the
documented set -- a wider BY list, a duplicate rule, a status column -- and it
is reported as two explicit lists rather than asserted in prose.

Usage:
  python code_fidelity.py                       # beside the note, the usual case
  python code_fidelity.py --sas path/to/prog.sas
  python code_fidelity.py --note path/to/index.html

Exit code is non-zero if any block differs or the diff is not the expected one.
"""
import argparse
import html
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)

# the note writes the extract by a generic name; the program has the study's own
SUBSTITUTIONS = [("raw.m2808P101_PT_INT", "raw.irt_kit")]

# the line ranges the note quotes, as (first, last) inclusive
RANGES = {
    "split": (331, 338),
    "dedup": (344, 346),
    "walk": (352, 384),
    "collapse": (390, 402),
}

# statements the hardening removes from the walk. Written in the spelling the
# note uses; norm() makes them comparable.
BEFORE_ONLY = [
    'put "Start: " i= scn_num= kit_num= kitnumrp=;',
    'put "Assign: " i= scn_num= kit_num= kitnumrp=;',
    'put "find: " i= scn_num= kit_num= kitnumrp= rc=;',
    'put "CAUTION: replacement kit not found...";',
    "drop i kitnumrp;",
    'by scn_num kit_num;',
    'declare hash h(dataset: "irt_rp");',
]


def read(p):
    s = open(p, encoding="utf-8", newline="").read()
    return s.replace("\r\n", "\n").replace("\r", "\n")


def lines(path, first, last):
    return "\n".join(read(path).split("\n")[first - 1:last])


def unstyled(block):
    """Markup out, entities back, the note's (12) markers gone."""
    t = re.sub(r"<[^>]+>", "", block)
    t = html.unescape(t)
    return re.sub(r"\(\d{1,2}\)", "", t)


def norm(text):
    """One canonical spelling for a SAS statement, format-blind but literal-aware."""
    t = text
    for a, b in SUBSTITUTIONS:
        t = re.sub(re.escape(a), b, t, flags=re.I)
    t = re.sub(r"/\*.*?\*/", " ", t, flags=re.S)          # /* ... */
    t = re.sub(r"^\s*\*[^;]*;", " ", t, flags=re.M)       # * banner ;
    literals = []

    def stash(m):
        literals.append(m.group(0))
        return "\x00%d\x00" % (len(literals) - 1)

    t = re.sub(r"'[^']*'|\"[^\"]*\"", stash, t)
    t = t.lower()
    t = re.sub(r"\s+", " ", t)
    t = re.sub(r"\s*([=(),;|])\s*", r"\1", t)
    t = re.sub(r"\s+", " ", t)
    for i, lit in enumerate(literals):
        t = t.replace("\x00%d\x00" % i, lit)
    return t.strip()


def statements(text):
    """Split on ; -- SAS statements, and keep the terminator."""
    return [norm(s) + ";" for s in text.split(";") if norm(s)]


def compare(label, note_text, file_text):
    a, b = statements(note_text), statements(file_text)
    print("\n%s" % label)
    print("  note %d statements, file %d statements" % (len(a), len(b)))
    bad = 0
    for i in range(max(len(a), len(b))):
        x = a[i] if i < len(a) else "<absent>"
        y = b[i] if i < len(b) else "<absent>"
        if x != y:
            bad += 1
            if bad <= 4:
                print("  DIFF at statement %d\n    note: %s\n    file: %s" % (i + 1, x, y))
    print("  -> %s" % ("%d statement(s) differ" % bad if bad
                       else "identical, statement for statement"))
    return bad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--note", default=os.path.join(REPO, "index.html"))
    ap.add_argument("--sas", default=os.path.join(REPO, "..", "..", "ec_template", "v_ec.sas"))
    args = ap.parse_args()

    for p in (args.note, args.sas):
        if not os.path.exists(p):
            sys.exit("cannot find %s" % os.path.abspath(p))

    source = read(args.note)
    found = [(m.start(), m.group(1))
             for m in re.finditer(r"<pre><code>(.*?)</code></pre>", source, re.S)]
    print("found %d code blocks in the note" % len(found))

    # the 5.5 listings live between the 5.5 and 5.6 headings
    s55 = source.find("5.5 Hardened chain step")
    s56 = source.find("5.6 The reference model")
    if s55 < 0 or s56 < s55:
        sys.exit("cannot locate the section 5.5 listings")
    pool = [unstyled(body) for off, body in found if s55 < off < s56]
    print("of which %d are the section 5.5 listings" % len(pool))

    def pick(*needles):
        hits = [b for b in pool if all(n in b for n in needles)]
        if len(hits) != 1:
            sys.exit("block selector %r matched %d blocks" % (needles, len(hits)))
        return hits[0]

    # the note prints the split and the deduplication as one block; the program
    # has them as two, so split the note's block on the sort
    one = pick("data irt_base irt_rp;", "output irt_base;")
    cut = one.find("proc sort")
    if cut < 0:
        sys.exit("cannot find the deduplication step inside the note's first block")
    note_split, note_dedup = one[:cut], one[cut:]
    note_walk = pick("data irt_chase;", "definedone();")

    fails = 0
    fails += compare("5.5 split        vs prog %d-%d" % RANGES["split"],
                     note_split, lines(args.sas, *RANGES["split"]))
    fails += compare("5.5 deduplicate  vs prog %d-%d" % RANGES["dedup"],
                     note_dedup, lines(args.sas, *RANGES["dedup"]))
    fails += compare("5.5 walk         vs prog %d-%d" % RANGES["walk"],
                     note_walk, lines(args.sas, *RANGES["walk"]))

    # -----------------------------------------------------------------------
    # what the hardening is, as a diff rather than as a claim
    # -----------------------------------------------------------------------
    before = next((b for b in [unstyled(x) for _o, x in found]
                   if 'put "Start: "' in b and "drop i kitnumrp;" in b), None)
    if before is None:
        sys.exit("cannot find the pre-hardening listing in the note")

    file_before = "\n".join(lines(args.sas, *RANGES[k])
                            for k in ("split", "dedup", "walk", "collapse"))
    file_after = "\n".join(lines(args.sas, *RANGES[k])
                           for k in ("split", "dedup", "walk"))
    b_s, all_s, hard_s = statements(before), statements(file_before), statements(file_after)

    added = [s for s in hard_s if s not in b_s]
    removed = [s for s in b_s if s not in all_s]

    print("\n" + "=" * 74)
    print("the hardening, as the difference between the two listings")
    print("=" * 74)
    print("\nadded -- %d statement(s) in the program, absent from the before-listing:"
          % len(added))
    for s in added:
        print("  + %s" % s)
    print("\nremoved -- %d statement(s) in the before-listing, gone from the program:"
          % len(removed))
    for s in removed:
        print("  - %s" % s)

    expected = set(norm(s) for s in BEFORE_ONLY)
    if set(removed) != expected:
        print("\nFAIL: the removals are not the documented set")
        for s in sorted(set(removed) - expected):
            print("  unexpected: %s" % s)
        for s in sorted(expected - set(removed)):
            print("  missing   : %s" % s)
        fails += 1
    else:
        print("\n-> the removals are exactly the documented set")

    if not any(s.startswith("by scn_num kit_num kitnumrp") for s in added):
        print("FAIL: the widened BY list is not among the additions")
        fails += 1
    if any(s.startswith("by scn_num kit_num;") for s in hard_s):
        print("FAIL: the program still carries the narrow BY list")
        fails += 1

    print("\n" + "=" * 74)
    print("code fidelity: %s" % ("PASS" if fails == 0 else "FAIL (%d)" % fails))
    return 0 if fails == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

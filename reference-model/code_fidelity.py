# -*- coding: utf-8 -*-
"""Is the code printed in the note the code in the program?

The note claims its listings are the program, not a paraphrase of it, and its
scenario matrix is the specification the shipped check asserts. Both are claims
about two files, so they are checked rather than trusted:

  part A  the six listings printed in section 3 of the note, against v_ec.sas
  part B  the step that kit_chain_check.sas runs, which must contain every
          statement of the program's four chain blocks
  part C  the dummy-data fixture printed in section 7.2, which must be the one
          the check loads
  part D  the scenario matrix in section 5.2, whose kit, lot, batch and probe
          count must be the expected table the check asserts

Comparison is case-folded, with comments, the note's own (12) markers and
whitespace dropped, so indentation and comment numbering are free to differ and
nothing else is. String literals are masked before the whitespace pass: `|| ', ' ||`
and `||','||` are the same statement, `', '` and `','` are not, and a checker that
could not tell those apart would wave through a wrong separator.

One substitution is expected and reported rather than treated as a difference:
the note writes the IRT extract as raw.irt_kit, the program has the study's own
name.

Usage:
  python code_fidelity.py                        # beside the note, the usual case
  python code_fidelity.py --sas path/to/v_ec.sas
  python code_fidelity.py --note path/to/index.html
  python code_fidelity.py --check path/to/kit_chain_check.sas

Exit code is non-zero if any block differs, any statement is missing, the
fixture has drifted, or the matrix disagrees with the check.
"""
import argparse
import html
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)

SUBSTITUTIONS = [("raw.m2808P101_PT_INT", "raw.irt_kit")]

# the program's line ranges, as (first, last) inclusive
RANGES = {
    "split":    (331, 338),
    "dedup":    (340, 346),
    "walk":     (352, 384),
    "collapse": (390, 402),
    "join":     (407, 412),
    "asgn":     (414, 425),
}

# selectors for the note's listings: (label, range, needles)
NOTE_BLOCKS = [
    ("listing 1  split",       "split",    ("data irt_base irt_rp;", "output irt_base;")),
    ("listing 2  dedup",       "dedup",    ("proc sort data = irt_rp nodupkey;",)),
    ("listing 3  walk",        "walk",     ("data irt_chase;", "definedone();")),
    ("listing 4  collapse",    "collapse", ("data irt_claps;", "if last.vis_type;")),
    ("listing 5  join",        "join",     ("create table ec_ext as",)),
    ("listing 5  identifiers", "asgn",     ("data ec_asgn;", "ecrefid")),
]


def read(p):
    return open(p, encoding="utf-8", newline="").read().replace("\r\n", "\n")


def lines(path, first, last):
    return "\n".join(read(path).split("\n")[first - 1:last])


def unstyled(block):
    """Markup out, entities back, the note's (12) markers gone."""
    t = re.sub(r"<[^>]+>", "", block)
    return re.sub(r"\(\d{1,2}\)", "", html.unescape(t))


def norm(text):
    """One canonical spelling for a SAS statement, format-blind but literal-aware."""
    t = text
    for a, b in SUBSTITUTIONS:
        t = re.sub(re.escape(a), b, t, flags=re.I)
    t = re.sub(r"/\*.*?\*/", " ", t, flags=re.S)
    t = re.sub(r"^\s*\*[^;]*;", " ", t, flags=re.M)
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


def datalines_block(text, anchor):
    """The rows between `datalines;` and the terminating `;` that follows it."""
    i = text.index(anchor)
    a = text.index("datalines;", i) + len("datalines;")
    b = text.index("\n;", a)
    return [ln for ln in text[a:b].strip("\n").splitlines() if ln.strip()]


def section(text, first, last):
    return text[text.index(first):text.index(last)]


TRIPLE = r"(\d+)\s*/\s*(LOT-[\w-]+)\s*/\s*(B[\w-]+)"


def matrix(note):
    """(case, {(kit, lot, batch)}, probes) for every row of the 5.2 matrix."""
    seg = section(note, "<h3>5.2", "<h3>5.3")
    out = []
    for tr in re.findall(r"<tr>(.*?)</tr>", seg, re.S):
        cells = [unstyled(c) for c in re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)]
        if len(cells) < 5 or not re.match(r"^S\d\d$", cells[0].strip()):
            continue
        hops = re.findall(r"\b(\d+)\b", cells[3])
        out.append((cells[0].strip(), set(re.findall(TRIPLE, cells[2])),
                    int(hops[0]) if hops else None))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--note", default=os.path.join(REPO, "index.html"))
    ap.add_argument("--sas", default=os.path.join(REPO, "..", "..", "ec_template", "v_ec.sas"))
    ap.add_argument("--check", default=os.path.join(REPO, "kit_chain_check.sas"))
    args = ap.parse_args()

    for p in (args.note, args.sas, args.check):
        if not os.path.exists(p):
            sys.exit("cannot find %s" % os.path.abspath(p))

    source = read(args.note)
    found = [(m.start(), m.group(1))
             for m in re.finditer(r"<pre><code>(.*?)</code></pre>", source, re.S)]
    print("found %d code blocks in the note" % len(found))
    pool = [unstyled(body) for _off, body in found]

    def pick(needles):
        hits = [b for b in pool if all(n.lower() in b.lower() for n in needles)]
        if len(hits) != 1:
            sys.exit("selector %r matched %d blocks" % (needles, len(hits)))
        return hits[0]

    fails = 0
    print("\n" + "=" * 74)
    print("part A  the note's own listings against the program")
    print("=" * 74)
    for label, key, needles in NOTE_BLOCKS:
        fails += compare("%s  vs prog %d-%d" % (label, *RANGES[key]),
                         pick(needles), lines(args.sas, *RANGES[key]))

    print("\n" + "=" * 74)
    print("part B  the step the check runs against the program")
    print("=" * 74)
    ver = read(args.check)
    if "%macro run_case" not in ver or "%mend run_case" not in ver:
        sys.exit("%s does not contain the run_case macro" % args.check)
    body = ver[ver.index("%macro run_case"):ver.index("%mend run_case")]
    body_st = set(statements(body))

    absent = substituted = counted = 0
    for key in ("split", "dedup", "walk", "collapse"):
        for st in statements(lines(args.sas, *RANGES[key])):
            counted += 1
            if st in body_st:
                continue
            if st.startswith("set raw."):
                print("  ~ substituted  : %s" % st)
                substituted += 1
                continue
            print("  X MISSING      : %s" % st)
            absent += 1
    print("  %d statements of the program looked for, %d absent, %d substituted"
          % (counted, absent, substituted))
    fails += absent

    print("\n" + "=" * 74)
    print("part C  the fixture printed in section 7.2 against the check's")
    print("=" * 74)
    want = datalines_block(ver, "data raw_kit;")
    hits = [b for b in pool
            if [ln for ln in b.splitlines() if ln.strip()] and
            [ln for ln in b.splitlines() if ln.strip()][0] == want[0]]
    if len(hits) != 1:
        print("  cannot locate the fixture in the note (%d hits)" % len(hits))
        fails += 1
    else:
        got = [ln for ln in hits[0].splitlines() if ln.strip()]
        bad = 0
        for i in range(max(len(got), len(want))):
            x = got[i] if i < len(got) else "<absent>"
            y = want[i] if i < len(want) else "<absent>"
            if x != y:
                bad += 1
                if bad <= 3:
                    print("  DIFF at line %d\n    note    : %s\n    verifier: %s" % (i + 1, x, y))
        print("  note %d lines, check %d lines -> %s"
              % (len(got), len(want), "identical" if not bad else "%d line(s) differ" % bad))
        fails += bad

    print("\n" + "=" * 74)
    print("part D  the scenario matrix in section 5.2 against the check's table")
    print("=" * 74)
    expect = {}
    for ln in datalines_block(ver, "data expect;"):
        case, scn, vis, kit, lot, btch, status, probes = [c.strip() for c in ln.split("|")]
        expect.setdefault(case, {"triples": set(), "probes": set()})
        expect[case]["triples"].add((kit, lot, btch))
        expect[case]["probes"].add(int(probes))
    bad = 0
    seen = set()
    for case, triples, hops in matrix(source):
        seen.add(case)
        if case not in expect:
            print("  %-5s in the matrix, no expected row -- correct for S14 and S15" % case)
            if triples:
                print("     but the matrix prints %s, which the check does not assert"
                      % sorted(triples))
                bad += 1
            continue
        want = expect[case]
        if triples != want["triples"]:
            print("  %-5s matrix %s, expected table %s"
                  % (case, sorted(triples), sorted(want["triples"])))
            bad += 1
        elif hops is not None and hops not in want["probes"]:
            print("  %-5s matrix hops %s, expected probes %s"
                  % (case, hops, sorted(want["probes"])))
            bad += 1
        else:
            print("  %-5s kit, lot, batch and probe count agree" % case)
    for case in sorted(expect):
        if case not in seen:
            print("  %-5s asserted by the check, missing from the matrix" % case)
            bad += 1
    print("  %d scenario rows compared, %d disagree" % (len(seen), bad))
    fails += bad

    print("\n" + "=" * 74)
    print("code fidelity: %s" % ("PASS" if fails == 0 else "FAIL (%d)" % fails))
    return 0 if fails == 0 else 1


if __name__ == "__main__":
    sys.exit(main())

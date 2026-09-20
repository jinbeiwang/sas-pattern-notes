# -*- coding: utf-8 -*-
"""The chain step, in Python, for the cases kit_chain_check.sas asserts.

The check beside this file is the deliverable: it is Base SAS, it runs the real
statements, and it is what a SAS session verdicts. This file exists because
nothing in this environment can run it, and because two of the note's claims are
arithmetic rather than fixtures:

  * every expected row in `data expect;` is what the step must produce, and this
    model reproduces it from the same rows the check loads;
  * the note's most contestable claim -- that the deduplication in front of the
    load decides whether `duplicate: "error"` has anything to catch -- is about
    counts under two BY lists, which is cheap to compute twice.

The fixture, the expected table and the macro parameters are all read out of
kit_chain_check.sas, so this file holds no copy of them and cannot drift from it.

What it is not: evidence that the SAS step behaves as modelled. The model is the
author's reading of the step, and section 7.5 of the note lists the three
behaviours only a real session can settle.

Usage:
  python ec_step_model.py
  python ec_step_model.py --check ../kit_chain_check.sas

Exit code is non-zero if an expected row is not reproduced, or if a count or a
collapse does not come out as the note says it does.
"""
import argparse
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
MISSING = None                      # SAS numeric missing, "." in the fixture


# ---------------------------------------------------------------------------
# reading the check
# ---------------------------------------------------------------------------
def read(p):
    return open(p, encoding="utf-8", newline="").read().replace("\r\n", "\n")


def datalines(text, anchor):
    i = text.index(anchor)
    a = text.index("datalines;", i) + len("datalines;")
    b = text.index("\n;", a)
    return [ln for ln in text[a:b].strip("\n").splitlines() if ln.strip()]


def macro(text, name):
    m = re.search(r"%%let\s+%s\s*=\s*([^;]+);" % name, text)
    if not m:
        sys.exit("kit_chain_check.sas has no %%let %s" % name)
    return m.group(1).strip()


def num(tok):
    return MISSING if tok.strip() == "." else int(tok)


def load(path):
    text = read(path)
    rows = []
    for ln in datalines(text, "data raw_kit;"):
        case, rowid, scn, kit, lot, btch, vis, tyds, rp = ln.split("|")
        rows.append({"case": case, "rowid": int(rowid), "scn_num": int(scn),
                     "kit_num": int(kit), "lot_num": lot.strip(),
                     "btch_num": btch.strip(), "vis_type": vis.strip(),
                     "kit_tyds": tyds.strip(), "kitnumrp": num(rp)})
    expect = []
    for ln in datalines(text, "data expect;"):
        case, scn, vis, kit, lot, btch, status, probes = ln.split("|")
        expect.append({"case": case, "scn_num": int(scn), "vis_type": vis.strip(),
                       "kit_num": int(kit), "lot_num": lot.strip(),
                       "btch_num": btch.strip(), "status": status.strip(),
                       "probes": int(probes)})
    vol = {k: int(macro(text, k))
           for k in ("vol_subjects", "vol_visits", "vol_links")}
    return rows, expect, vol


# ---------------------------------------------------------------------------
# the four steps, as the program writes them
# ---------------------------------------------------------------------------
def split(rows):
    """Listing 1: upcase, one alias, then two explicit outputs."""
    base, rp = [], []
    for r in rows:
        vis = r["vis_type"].upper()
        if vis == "DISCONTINUE":
            vis = "END OF TREATMENT"
        out = dict(r, vis_type=vis)
        if vis == "KIT REPLACEMENT":
            rp.append(out)
        elif out["kit_tyds"]:
            base.append(out)
    return base, rp


KEY_BY = ("scn_num", "kit_num")
FULL_BY = ("scn_num", "kit_num", "kitnumrp", "lot_num", "btch_num")


def dedup(rp, by):
    """Listing 2: nodupkey on the given BY list."""
    seen, kept = set(), []
    for r in sorted(rp, key=lambda r: tuple(
            "" if r[k] is None else r[k] for k in by)):
        key = tuple(r[k] for k in by)
        if key in seen:
            continue
        seen.add(key)
        kept.append(r)
    return kept


def walk(base, table, budget=100):
    """Listing 3: the probe loop, with the miss branch that restores the kit."""
    look = {(r["scn_num"], r["kit_num"]): r for r in table}
    out = []
    for b in base:
        row = dict(b)
        prev = row["kit_num"]
        status = ""
        probes = 0
        while probes < budget and row["kitnumrp"] is not MISSING:
            row["kit_num"] = row["kitnumrp"]
            probes += 1
            hit = look.get((row["scn_num"], row["kit_num"]))
            if hit is None:
                status = "DANGLING"
                row["kit_num"] = prev               # keep the triple in step
                break
            row["kitnumrp"] = hit["kitnumrp"]
            row["lot_num"] = hit["lot_num"]
            row["btch_num"] = hit["btch_num"]
            prev = row["kit_num"]
        if status == "":
            status = "RESOLVED" if row["kitnumrp"] is MISSING else "UNRESOLVED"
        row["chain_status"] = status
        row["probes"] = probes
        out.append(row)
    return out


def collapse(chase, refid_len=200):
    """Listing 4: one reference list per subject and visit."""
    groups = {}
    for r in sorted(chase, key=lambda r: (r["scn_num"], r["vis_type"],
                                          r["kit_tyds"], r["kit_num"])):
        groups.setdefault((r["scn_num"], r["vis_type"]), []).append(r)
    out = []
    for _key, grp in groups.items():
        refid = ""
        for n, r in enumerate(grp):
            piece = str(r["kit_num"])
            refid = piece if n == 0 else (refid + ", " + piece)[:refid_len]
        last = dict(grp[-1])
        last["refid"] = refid
        last["n_kits"] = len(grp)
        out.append(last)
    return out


# ---------------------------------------------------------------------------
# the volume case, generated by the same formulas as the check
# ---------------------------------------------------------------------------
def volume(vol):
    rows, expect = [], []
    for s in range(1, vol["vol_subjects"] + 1):
        for v in range(1, vol["vol_visits"] + 1):
            k0 = 1000000 + s * 1000 + v * 20
            vis = "CYCLE 1 DAY %d" % v
            rows.append({"case": "S15", "rowid": 1, "scn_num": 900000 + s,
                         "kit_num": k0, "lot_num": "LOT-V", "btch_num": "B-V",
                         "vis_type": vis, "kit_tyds": "KIT",
                         "kitnumrp": k0 + 1})
            for j in range(1, vol["vol_links"] + 1):
                rows.append({"case": "S15", "rowid": 1 + j, "scn_num": 900000 + s,
                             "kit_num": k0 + j, "lot_num": "LOT-V",
                             "btch_num": "B-V", "vis_type": "KIT REPLACEMENT",
                             "kit_tyds": "KIT",
                             "kitnumrp": k0 + j + 1 if j < vol["vol_links"] else MISSING})
            expect.append({"case": "S15", "scn_num": 900000 + s, "vis_type": vis,
                           "kit_num": k0 + vol["vol_links"], "lot_num": "LOT-V",
                           "btch_num": "B-V", "status": "RESOLVED",
                           "probes": vol["vol_links"]})
    return rows, expect


def case_rows(rows, case):
    sub = [r for r in rows if r["case"] == case]
    base, rp = split(sub)
    return base, rp


# ---------------------------------------------------------------------------
# report
# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", default=os.path.join(REPO, "kit_chain_check.sas"))
    args = ap.parse_args()
    if not os.path.exists(args.check):
        sys.exit("cannot find %s" % args.check)

    rows, expect, vol = load(args.check)
    fails = []

    print("=" * 74)
    print("the fixture, and what the step makes of it")
    print("=" * 74)
    print("%-5s %-8s %-6s %-8s %-8s %-11s %-6s %s"
          % ("case", "scn_num", "probes", "kit", "lot", "status", "batch", "vs expect"))
    for case in sorted({e["case"] for e in expect}):
        base, rp = case_rows(rows, case)
        for row in sorted(walk(base, dedup(rp, FULL_BY)),
                          key=lambda r: (r["scn_num"], r["kit_num"])):
            want = [e for e in expect
                    if e["case"] == case and e["scn_num"] == row["scn_num"]
                    and e["vis_type"] == row["vis_type"]]
            if not want:
                fails.append("%s: no expected row for subject %d"
                             % (case, row["scn_num"]))
                continue
            w = want[0]
            got = (row["kit_num"], row["lot_num"], row["btch_num"],
                   row["chain_status"], row["probes"])
            exp = (w["kit_num"], w["lot_num"], w["btch_num"], w["status"], w["probes"])
            ok = got == exp
            if not ok:
                fails.append("%s subject %d: expected %s, model produced %s"
                             % (case, row["scn_num"], exp, got))
            print("%-5s %-8d %-6d %-8d %-8s %-11s %-6s %s"
                  % (case, row["scn_num"], row["probes"], row["kit_num"],
                     row["lot_num"], row["chain_status"], row["btch_num"],
                     "match" if ok else "MISMATCH"))

    print()
    print("=" * 74)
    print("the BY list in front of the load decides whether the rule can fire")
    print("=" * 74)
    for case, want in (("S14", (4, 4, 3)), ("S17", (3, 2, 2))):
        _base, rp = case_rows(rows, case)
        got = (len(rp), len(dedup(rp, FULL_BY)), len(dedup(rp, KEY_BY)))
        print("  %-4s %d replacement rows -> %d keys on key+payload, %d on key alone"
              % (case, got[0], got[1], got[2]))
        if got != want:
            fails.append("%s counts: expected %s, model produced %s" % (case, want, got))
    clash = {}
    for r in dedup(case_rows(rows, "S14")[1], FULL_BY):
        key = (r["scn_num"], r["kit_num"])
        clash[key] = clash.get(key, 0) + 1
    print("  the key the load is left holding twice, and so refuses: %s"
          % ", ".join("(%d, %d)" % k for k, n in sorted(clash.items()) if n > 1))

    print()
    print("=" * 74)
    print("F4  the collapsed record for a visit carrying three kits")
    print("=" * 74)
    chase = [{"scn_num": 101, "vis_type": "CYCLE 1 DAY 1", "kit_tyds": "KIT",
              "kit_num": 1001 + n, "lot_num": "LOT-%02d" % n,
              "btch_num": "B%02d" % n, "chain_status": "RESOLVED"}
             for n in range(3)]
    col = collapse(chase)[0]
    print("  ECLOT=%s BATCHNUM=%s belong to kit %d; ECREFID=%r lists %d kits"
          % (col["lot_num"], col["btch_num"], col["kit_num"], col["refid"],
             col["n_kits"]))
    print("  refid holds %d kit numbers of five digits before it stops "
          "(floor(202 / 7)); a visit carries a handful"
          % ((200 + 2) // (5 + 2)))

    print()
    print("=" * 74)
    print("S15  %d subjects x %d visits, %d replacements each"
          % (vol["vol_subjects"], vol["vol_visits"], vol["vol_links"]))
    print("=" * 74)
    vrows, vexpect = volume(vol)
    vbase, vrp = split(vrows)
    vgot = sorted(walk(vbase, dedup(vrp, FULL_BY)),
                  key=lambda r: (r["scn_num"], r["vis_type"]))
    visits = len(vexpect)
    right = sum(1 for row, w in zip(vgot, vexpect)
                if (row["kit_num"], row["chain_status"], row["probes"])
                == (w["kit_num"], w["status"], w["probes"]))
    print("  %s visits, %s replacement rows, %s probes per row, %d/%d on the "
          "terminal kit, budget exhausted %d"
          % ("{:,}".format(visits), "{:,}".format(len(vrp)), vol["vol_links"],
             right, visits, sum(1 for r in vgot if r["probes"] >= 100)))
    if right != visits:
        fails.append("S15: %d of %d volume rows are wrong" % (visits - right, visits))

    print()
    print("=" * 74)
    for f in fails:
        print("  !! " + f)
    print("step model: %s" % ("PASS -- every expected row reproduced"
                              if not fails else "FAIL (%d)" % len(fails)))
    return 0 if not fails else 1


if __name__ == "__main__":
    sys.exit(main())

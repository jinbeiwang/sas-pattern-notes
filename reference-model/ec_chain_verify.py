#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Executable reference model and test harness for the chained kit-replacement step
of the SDTM EC validation program (ECREFID / ECLOT / BATCHNUM).

No SAS session is needed. The DATA step constructs that matter are emulated
explicitly, because each one is load-bearing for the result:

  * PDV persistence
      Variables are NOT reset between DATA step iterations. Only the `set`
      statement re-assigns on every iteration; every other variable keeps its
      value -- which is exactly why a hash payload survives a missed probe.

  * hash load
      The table is built when the object is defined, from whatever rows the
      preceding sort/dedup step produced.

  * find()
      On a HIT the definedata variables are copied into the PDV and 0 is
      returned. On a MISS the PDV is left completely untouched and a non-zero
      code is returned. Nothing is nulled out for you.

  * duplicate:
      Default (unset) keeps the FIRST row loaded for a repeated key and writes
      nothing to the log. 'replace' keeps the last. 'error' stops the load.

  * do i = 1 to 100 while (cond)
      The WHILE test is evaluated before every iteration, including the first,
      and the index is a hard budget as well.

  * length $200
      Character assignment in SAS truncates silently to the declared length.

  * proc sort ... nodupkey
      Keeps the first row of each BY group, in the physical order of the input
      (the sort is stable).

Usage:  python ec_chain_verify.py            # run all rounds, print the report
        python ec_chain_verify.py --json     # same, plus a JSON summary
"""

import json
import sys

# ----------------------------------------------------------------------------
# missing-value handling
# ----------------------------------------------------------------------------
# SAS numeric missing (.) and character missing (blank) both map to Python None.


def ismissing(v):
    return v is None or (isinstance(v, str) and v.strip() == "")


# ----------------------------------------------------------------------------
# hash object
# ----------------------------------------------------------------------------
class DuplicateKeyError(Exception):
    """Raised by the load when duplicate:'error' meets a repeated key."""

    def __init__(self, key):
        super().__init__("ERROR: Duplicate key %r on hash load" % (key,))
        self.key = key


class LoadRefused(Exception):
    """The load refused to complete, so the DATA step produced nothing."""


class Hash:
    def __init__(self, rows, keys, data, duplicate=None):
        self.keys = tuple(keys)
        self.data = tuple(data)
        self.duplicate = duplicate
        self.table = {}
        self.load_stats = {"rows_in": 0, "entries": 0, "duplicates": 0,
                           "kept_first": 0, "kept_last": 0}
        self._load(rows)

    def _load(self, rows):
        for r in rows:
            self.load_stats["rows_in"] += 1
            k = tuple(r.get(v) for v in self.keys)
            payload = {v: r.get(v) for v in self.data}
            if k in self.table:
                self.load_stats["duplicates"] += 1
                if self.duplicate in ("error", "e"):
                    raise DuplicateKeyError(k)
                if self.duplicate in ("replace", "r"):
                    self.table[k] = payload
                    self.load_stats["kept_last"] += 1
                    continue
                # default and 'nodupkey'-style: first row wins, silently
                self.load_stats["kept_first"] += 1
                continue
            self.table[k] = payload
        self.load_stats["entries"] = len(self.table)

    def find(self, pdv):
        k = tuple(pdv.get(v) for v in self.keys)
        payload = self.table.get(k)
        if payload is None:
            return 1                      # miss: PDV untouched
        pdv.update(payload)               # hit: payload written back
        return 0

    def find_next(self, pdv):
        # Not used by this pattern; kept so the emulation is not silently
        # pretending to be a complete hash implementation.
        raise NotImplementedError("find_next is out of scope for this model")


# ----------------------------------------------------------------------------
# formatting helpers that mirror the SAS code
# ----------------------------------------------------------------------------
def best(v):
    """strip(put(v, best.)) for the integer kit numbers in this data."""
    return "" if ismissing(v) else str(int(v))


def trunc(s, n):
    """length $n assignment."""
    return (s or "")[:n]


# ----------------------------------------------------------------------------
# step 1/2 -- split the IRT feed, then deduplicate
# ----------------------------------------------------------------------------
KEEP = ("scn_num", "kit_tyds", "kit_num", "lot_num", "vis_type",
        "btch_num", "kitnumrp")


def step_split(raw, dedup_by=("scn_num", "kit_num")):
    """data irt_base irt_rp; ...  followed by  proc sort nodupkey."""

    base, rp = [], []
    for r in raw:
        vis = r["vis_type"]
        vis = vis.upper() if not ismissing(vis) else None
        if vis == "DISCONTINUE":
            vis = "END OF TREATMENT"
        row = {k: r.get(k) for k in KEEP}
        row["rowid"] = r["rowid"]
        row["scenario"] = r["scenario"]
        row["vis_type"] = vis
        if vis == "KIT REPLACEMENT":
            rp.append(row)
        elif not ismissing(row["kit_tyds"]):
            base.append(row)

    # proc sort nodupkey; by scn_num kit_num;   (stable => physical order wins)
    seen, deduped = set(), []
    for r in sorted(rp, key=lambda x: tuple(str(x[k]) for k in dedup_by)):
        k = tuple(r[k] for k in dedup_by)
        if k in seen:
            continue
        seen.add(k)
        deduped.append(r)
    return base, rp, deduped


# ----------------------------------------------------------------------------
# the chain walk -- original listing and the hardened step
# ----------------------------------------------------------------------------
def walk(base, rp_table, hardened=False, trace=False):
    """data irt_chase; ... run;"""

    dup = "error" if hardened else None
    out = []
    created = {"rows_in": len(rp_table), "entries": 0, "duplicates": 0}

    try:
        h = Hash(rp_table, keys=("scn_num", "kit_num"),
                 data=("kitnumrp", "lot_num", "btch_num"), duplicate=dup)
        created = h.load_stats
    except DuplicateKeyError as e:
        # the load failed: SAS reports the duplicate and stops the DATA step,
        # so nothing is produced at all. That is the point of the guardrail.
        raise LoadRefused(str(e))

    for b in base:
        pdv = dict(b)
        probes = 0
        diag = 0
        chain_status = None

        if hardened:
            chain_status = ""
            prev_kit = pdv["kit_num"]

        for i in range(1, 101):                       # do i = 1 to 100 ...
            if ismissing(pdv["kitnumrp"]):             # ... while (not missing)
                break
            pdv["kit_num"] = pdv["kitnumrp"]           # pointer moves first
            probes += 1
            rc = h.find(pdv)
            if trace:
                print("   i=%2d kit_num=%-6s kitnumrp=%-6s rc=%d"
                      % (i, best(pdv["kit_num"]), best(pdv["kitnumrp"]), rc))
            if rc != 0:                                 # miss
                if hardened:
                    chain_status = "DANGLING"
                    pdv["kit_num"] = prev_kit           # keep kit+lot+batch together
                    break
                diag += 1                               # the original's CAUTION line
                break
            if hardened:
                prev_kit = pdv["kit_num"]

        if hardened:
            if chain_status == "":
                chain_status = ("RESOLVED" if ismissing(pdv["kitnumrp"])
                                else "UNRESOLVED")
            if chain_status != "RESOLVED":
                diag += 1                               # the conditional put

        row = dict(pdv)
        row["probes"] = probes
        row["diagnostics"] = diag
        if hardened:
            row["chain_status"] = chain_status
        out.append(row)

    return out, created


# ----------------------------------------------------------------------------
# step 4 -- collapse to one row per subject and visit
# ----------------------------------------------------------------------------
def collapse(chase, refid_len=200):
    """proc sort; data irt_claps; ... if last.vis_type; run;"""

    rows = sorted(chase, key=lambda r: (str(r["scn_num"]), str(r["vis_type"]),
                                        str(r["kit_tyds"]), int(r["kit_num"])))
    out, i = [], 0
    while i < len(rows):
        j = i
        key = (rows[i]["scn_num"], rows[i]["vis_type"])
        while j < len(rows) and (rows[j]["scn_num"], rows[j]["vis_type"]) == key:
            j += 1
        grp = rows[i:j]
        refid = ""
        for n, r in enumerate(grp):
            piece = best(r["kit_num"])
            refid = piece if n == 0 else trunc(refid + ", " + piece, refid_len)
            refid = trunc(refid, refid_len)
        last = grp[-1]
        out.append({
            "scn_num": last["scn_num"], "vis_type": last["vis_type"],
            "kit_tyds": last["kit_tyds"], "kit_num": last["kit_num"],
            "lot_num": last["lot_num"], "btch_num": last["btch_num"],
            "refid": refid, "n_kits": len(grp),
            "refid_len": len(refid),
            "chain_status": last.get("chain_status"),
        })
        i = j
    return out


# ----------------------------------------------------------------------------
# the synthetic feed, exactly as published in the note
# ----------------------------------------------------------------------------
RAW = """
S01|1|101|1001|LOT-A|B01|CYCLE 1 DAY 1|KIT|.
S02|1|101|1001|LOT-A|B01|CYCLE 1 DAY 1|KIT|1002
S02|2|101|1002|LOT-B|B02|KIT REPLACEMENT|KIT|.
S03|1|101|1001|LOT-A|B01|CYCLE 1 DAY 1|KIT|1002
S03|2|101|1002|LOT-B|B02|KIT REPLACEMENT|KIT|1003
S03|3|101|1003|LOT-C|B03|KIT REPLACEMENT|KIT|1004
S03|4|101|1004|LOT-D|B04|KIT REPLACEMENT|KIT|.
S04|1|101|1001|LOT-A|B01|CYCLE 1 DAY 1|KIT|1002
S04|2|101|1002|LOT-B|B02|KIT REPLACEMENT|KIT|1003
S04|3|101|1003|LOT-C|B03|KIT REPLACEMENT|KIT|1004
S04|4|101|1004|LOT-D|B04|KIT REPLACEMENT|KIT|1005
S04|5|101|1005|LOT-E|B05|KIT REPLACEMENT|KIT|1006
S04|6|101|1006|LOT-F|B06|KIT REPLACEMENT|KIT|1007
S04|7|101|1007|LOT-G|B07|KIT REPLACEMENT|KIT|1008
S04|8|101|1008|LOT-H|B08|KIT REPLACEMENT|KIT|1009
S04|9|101|1009|LOT-I|B09|KIT REPLACEMENT|KIT|.
S05|1|101|1001|LOT-A|B01|CYCLE 1 DAY 1|KIT|9001
S05|2|101|1002|LOT-B|B02|KIT REPLACEMENT|KIT|.
S06|1|101|1001|LOT-A|B01|CYCLE 1 DAY 1|KIT|1002
S06|2|101|1002|LOT-B|B02|KIT REPLACEMENT|KIT|1099
S07|1|101|1001|LOT-A|B01|CYCLE 1 DAY 1|KIT|1002
S07|2|101|1002|LOT-B|B02|KIT REPLACEMENT|KIT|1003
S07|3|101|1003|LOT-C|B03|KIT REPLACEMENT|KIT|1002
S08|1|101|1001|LOT-A|B01|CYCLE 1 DAY 1|KIT|1002
S08|2|101|1002|LOT-S|B-S|KIT REPLACEMENT|KIT|1002
S09|1|101|1001|LOT-A|B01|CYCLE 1 DAY 1|KIT|.
S09|2|101|1001|LOT-B|B02|KIT REPLACEMENT|KIT|1002
S10|1|101|1001|LOT-A|B01|CYCLE 1 DAY 1|KIT|1002
S11|1|101|1001|LOT-A|B01|CYCLE 1 DAY 1|KIT|1002
S11|2|101|1002|LOT-T1|BT1|KIT REPLACEMENT|KIT|.
S11|3|202|2001|LOT-X|B91|CYCLE 1 DAY 1|KIT|1002
S11|4|202|1002|LOT-T2|BT2|KIT REPLACEMENT|KIT|.
S12|1|101|1001|LOT-A|B01|discontinue|KIT|1002
S12|2|101|1002|LOT-B|B02|kit replacement|KIT|.
S13|1|101|1001|LOT-A|B01|SCREENING| |.
S14|1|101|1001|LOT-A|B01|CYCLE 1 DAY 1|KIT|1002
S14|2|101|1002|LOT-B1|B02|KIT REPLACEMENT|KIT|1003
S14|3|101|1002|LOT-B2|B03|KIT REPLACEMENT|KIT|1004
S14|4|101|1003|LOT-T3|BT3|KIT REPLACEMENT|KIT|.
S14|5|101|1004|LOT-T4|BT4|KIT REPLACEMENT|KIT|.
S17|1|101|1001|LOT-A|B01|CYCLE 1 DAY 1|KIT|1002
S17|2|101|1002|LOT-B|B02|KIT REPLACEMENT|KIT|1003
S17|3|101|1002|LOT-B|B02|KIT REPLACEMENT|KIT|1003
S17|4|101|1003|LOT-C|B03|KIT REPLACEMENT|KIT|.
"""


def parse_raw(txt, swap_s14=False):
    lines = [l.strip() for l in txt.strip().splitlines() if l.strip()]
    if swap_s14:                       # reproduce F3 by reordering rows
        lines = ["%s|%s" % (l.split("|")[0], l.split("|")[1]) if False else l
                 for l in lines]
        i2 = next(i for i, l in enumerate(lines) if l.startswith("S14|2|"))
        i3 = next(i for i, l in enumerate(lines) if l.startswith("S14|3|"))
        lines[i2], lines[i3] = lines[i3], lines[i2]
    rows = []
    for ln in lines:
        sc, rowid, scn, kit, lot, btch, vis, tyds, rp = ln.split("|")
        rows.append({
            "scenario": sc, "rowid": int(rowid), "scn_num": int(scn),
            "kit_num": int(kit), "lot_num": lot.strip() or None,
            "btch_num": btch.strip() or None, "vis_type": vis.strip() or None,
            "kit_tyds": tyds.strip() or None,
            "kitnumrp": None if rp.strip() in (".", "") else int(rp),
        })
    return rows


# ----------------------------------------------------------------------------
# Round 1 -- fidelity: reproduce what the note already published
# ----------------------------------------------------------------------------
PUBLISHED = {
    # scenario, rowid -> (kit_num, lot, batch, status_or_None, probes)
    ("S01", 1): (1001, "LOT-A", "B01", None, 0),
    ("S02", 1): (1002, "LOT-B", "B02", None, 1),
    ("S03", 1): (1004, "LOT-D", "B04", None, 3),
    ("S04", 1): (1009, "LOT-I", "B09", None, 8),
    ("S05", 1): (9001, "LOT-A", "B01", None, 1),
    ("S06", 1): (1099, "LOT-B", "B02", None, 2),
    ("S07", 1): (1003, "LOT-C", "B03", None, 100),
    ("S08", 1): (1002, "LOT-S", "B-S", None, 100),
    ("S09", 1): (1001, "LOT-A", "B01", None, 0),
    ("S10", 1): (1002, "LOT-A", "B01", None, 1),
    ("S11", 1): (1002, "LOT-T1", "BT1", None, 1),
    ("S11", 3): (1002, "LOT-T2", "BT2", None, 1),
    ("S12", 1): (1002, "LOT-B", "B02", None, 1),
    ("S14", 1): (1003, "LOT-T3", "BT3", None, 2),
}


def run_scenario(raw_rows, scen, hardened, dedup_by):
    sub = [r for r in raw_rows if r["scenario"] == scen]
    base, _rp, deduped = step_split(sub, dedup_by=dedup_by)
    return walk(base, deduped, hardened=hardened)


def round1_fidelity():
    raw = parse_raw(RAW)
    got, failures = [], []
    published_scen = {s for (s, _r) in PUBLISHED}
    for scen in sorted({r["scenario"] for r in raw}):
        if scen not in published_scen:              # structural / added later
            continue
        base, _, deduped = step_split([r for r in raw if r["scenario"] == scen])
        rows, _ = walk(base, deduped, hardened=False)
        for r in rows:
            key = (scen, r["rowid"])
            if key not in PUBLISHED:
                failures.append("%s: unexpected extra row %s" % (scen, r))
                continue
            e_kit, e_lot, e_btch, _st, e_pr = PUBLISHED[key]
            actual = (r["kit_num"], r["lot_num"], r["btch_num"], r["probes"])
            want = (e_kit, e_lot, e_btch, e_pr)
            status = "match" if actual == want else "MISMATCH"
            if actual != want:
                failures.append("%s row %d: want %s got %s" % (scen, r["rowid"], want, actual))
            got.append((scen, r["rowid"], actual, status))
        # rows published but not produced
        for (s2, rid) in PUBLISHED:
            if s2 == scen and not any(x["rowid"] == rid for x in rows):
                failures.append("%s row %d: expected row not produced" % (s2, rid))
    return got, failures


# ----------------------------------------------------------------------------
# Round 2/3 -- the hardened step, before and after closing F3
# ----------------------------------------------------------------------------
def round2_and_3():
    raw = parse_raw(RAW)
    result = {}
    for label, dedup_by in (
            ("template", ("scn_num", "kit_num")),
            ("extended", ("scn_num", "kit_num", "kitnumrp", "lot_num", "btch_num"))):
        per = {}
        for scen in sorted({r["scenario"] for r in raw}):
            sub = [r for r in raw if r["scenario"] == scen]
            base, rp, deduped = step_split(sub, dedup_by=dedup_by)
            try:
                rows, load = walk(base, deduped, hardened=True)
            except LoadRefused as e:
                per[scen] = {"load_refused": str(e), "rows": [],
                             "n_rp_raw": len(rp), "n_dedup": len(deduped)}
                continue
            per[scen] = {"load_refused": None, "rows": [dict(r) for r in rows],
                         "load": load, "n_base": len(base),
                         "n_rp_raw": len(rp), "n_dedup": len(deduped)}
        result[label] = per
    return result


def s14_order_test(dedup_by):
    """F3: does swapping two conflicting rows change the answer?"""
    out = {}
    for tag, swap in (("as given", False), ("swapped", True)):
        raw = parse_raw(RAW, swap_s14=swap)
        base, _, deduped = step_split([r for r in raw if r["scenario"] == "S14"],
                                      dedup_by=dedup_by)
        try:
            rows, _ = walk(base, deduped, hardened=True)
            out[tag] = (rows[0]["kit_num"], rows[0]["lot_num"],
                        rows[0]["chain_status"])
        except LoadRefused as e:
            out[tag] = ("REFUSED", str(e), "REFUSED")
    return out


# ----------------------------------------------------------------------------
# collapse-level measurements (F4, F5)
# ----------------------------------------------------------------------------
def refid_capacity():
    """F5: how many whole kit numbers fit in length refid $200?"""
    table = []
    for width in (3, 4, 5, 6):
        first = 10 ** (width - 1)
        kits = [first + n for n in range(80)]
        chase = [{"scn_num": 101, "vis_type": "CYCLE 1 DAY 1", "kit_tyds": "KIT",
                  "kit_num": k, "lot_num": "LOT-A", "btch_num": "B01",
                  "chain_status": "RESOLVED"} for k in kits]
        col = collapse(chase)[0]
        whole = col["refid"].count(",") + 1
        if col["refid_len"] >= 200:
            whole -= 1                                # last entry is a fragment
        table.append({"width": width, "kits": len(kits),
                      "whole_entries": whole,
                      "refid_len": col["refid_len"],
                      "truncated": col["refid_len"] >= 200,
                      "formula": (200 + 2) // (width + 2)})
    return table


def cardinality_case(n_kits=80):
    """F4: ECREFID describes every kit, ECLOT/BATCHNUM belong to one."""
    chase = [{"scn_num": 101, "vis_type": "CYCLE 1 DAY 1", "kit_tyds": "KIT",
              "kit_num": 1001 + n, "lot_num": "LOT-%02d" % n,
              "btch_num": "B%02d" % n, "chain_status": "RESOLVED"}
             for n in range(n_kits)]
    col = collapse(chase)[0]
    pieces = col["refid"].split(", ")
    complete = sum(1 for p in pieces if len(p) == 4)
    return {"kits_in_visit": n_kits,
            "refid_complete": complete,
            "refid_fragment": len(pieces) - complete,
            "refid_len": col["refid_len"],
            "eclot": col["lot_num"], "batchnum": col["btch_num"],
            "eclot_belongs_to_kit": int(col["kit_num"])}


def s16_join_case():
    """F6: the two sides normalise the visit label differently."""
    def irt_side(v):
        v = v.upper()
        return "END OF TREATMENT" if v == "DISCONTINUE" else v

    def crf_side(v):
        v = v.upper()
        return "END OF TREATMENT" if "DISCONT" in v else v

    out = []
    for label in ("DISCONTINUE", "DISCONTINUED", "END OF TREATMENT",
                  "CYCLE 1 DAY 1"):
        i, c = irt_side(label), crf_side(label)
        out.append({"label": label, "irt_side": i, "crf_side": c,
                    "join": "hit" if i == c else "MISS"})
    return out


def volume_case(subjects=5000, visits=4, links=11):
    """S15: cost is flat in chain depth."""
    base, rp = [], []
    lot_of = {}                                  # kit -> (lot, batch)
    for s in range(subjects):
        for v in range(visits):
            # a kit number identifies a physical kit, so each visit gets its
            # own block of numbers -- overlapping blocks would collide on the
            # (scn_num, kit_num) key, which is a separate design point.
            first = 100000 + s * 1000 + v * 20
            for n in range(links + 1):
                k = first + n
                lot_of[k] = ("LOT-%05d-%02d" % (s, n), "B%02d" % n)
                rp.append({"scn_num": 100000 + s, "kit_num": k, "kit_tyds": "KIT",
                           "lot_num": lot_of[k][0], "btch_num": lot_of[k][1],
                           "kitnumrp": (first + n + 1) if n < links else None})
            base.append({"scn_num": 100000 + s, "kit_num": first, "kit_tyds": "KIT",
                         "lot_num": lot_of[first][0], "btch_num": lot_of[first][1],
                         "vis_type": "CYCLE 1 DAY 1", "kitnumrp": first + 1,
                         "rowid": v + 1})
    rows, load = walk(base, rp, hardened=True)
    good = 0
    for r, b in zip(rows, base):
        want = b["kit_num"] + links
        if r["kit_num"] == want and r["chain_status"] == "RESOLVED" \
                and r["lot_num"] == lot_of[want][0] and r["btch_num"] == lot_of[want][1]:
            good += 1
    return {"visits": len(base), "replacement_rows": len(rp),
            "entries_loaded": load["entries"], "probes_per_row": rows[0]["probes"],
            "correct": good, "budget_exhausted": sum(
                1 for r in rows if r["chain_status"] == "UNRESOLVED")}


def structure_case_s13():
    raw = [r for r in parse_raw(RAW) if r["scenario"] == "S13"]
    base, rp, ded = step_split(raw)
    return {"rows_in_feed": len(base), "rows_in_rp": len(rp)}


# ----------------------------------------------------------------------------
# report
# ----------------------------------------------------------------------------
def main():
    as_json = "--json" in sys.argv
    summary = {}

    print("=" * 78)
    print("ROUND 1  fidelity -- does the model reproduce what the note published?")
    print("=" * 78)
    got, failures = round1_fidelity()
    print("%-6s %-6s %-8s %-10s %-6s %-8s %s"
          % ("scen", "rowid", "kit_num", "lot_num", "batch", "probes", "vs note"))
    for scen, rid, actual, status in got:
        print("%-6s %-6d %-8d %-10s %-6s %-8d %s"
              % (scen, rid, actual[0], actual[1], actual[2], actual[3], status))
    print("\npublished rows reproduced : %d / %d" % (len(got) - len(failures), len(got)))
    for f in failures:
        print("   !! " + f)
    summary["round1"] = {"rows": len(got), "mismatches": failures}

    print()
    print("=" * 78)
    print("ROUND 2  hardened step as applied in the template")
    print("=" * 78)
    res = round2_and_3()
    order = sorted({r["scenario"] for r in parse_raw(RAW)})
    for scen in order:
        t = res["template"][scen]
        if t["load_refused"]:
            print("%-5s load refused: %s" % (scen, t["load_refused"]))
            continue
        for r in t["rows"]:
            print("%-5s row %d  kit=%-6s lot=%-8s batch=%-6s status=%-11s probes=%d"
                  % (scen, r["rowid"], best(r["kit_num"]), r["lot_num"],
                     r["btch_num"], r["chain_status"], r["probes"]))
    summary["round2"] = {s: {"load_refused": res["template"][s]["load_refused"],
                             "rows": [{k: v for k, v in r.items() if k in
                                       ("rowid", "kit_num", "lot_num", "btch_num",
                                        "chain_status", "probes")}
                                      for r in res["template"][s]["rows"]]}
                         for s in order}

    print()
    print("=" * 78)
    print("ROUND 3  the same scenarios with the dedup BY list extended")
    print("=" * 78)
    for scen in order:
        t = res["extended"][scen]
        if t["load_refused"]:
            print("%-5s load refused: %s" % (scen, t["load_refused"]))
            continue
        for r in t["rows"]:
            print("%-5s row %d  kit=%-6s lot=%-8s batch=%-6s status=%-11s probes=%d"
                  % (scen, r["rowid"], best(r["kit_num"]), r["lot_num"],
                     r["btch_num"], r["chain_status"], r["probes"]))
    summary["round3"] = {s: {"load_refused": res["extended"][s]["load_refused"],
                             "rows": [{k: v for k, v in r.items() if k in
                                       ("rowid", "kit_num", "lot_num", "btch_num",
                                        "chain_status", "probes")}
                                      for r in res["extended"][s]["rows"]]}
                         for s in order}

    print()
    print("=" * 78)
    print("F3  order dependence of the deduplication")
    print("=" * 78)
    for label, by in (("template", ("scn_num", "kit_num")),
                      ("extended", ("scn_num", "kit_num", "kitnumrp",
                                    "lot_num", "btch_num"))):
        o = s14_order_test(by)
        print("%-9s as given -> %-28s | swapped -> %s"
              % (label, str(o["as given"]), str(o["swapped"])))
    print()
    print("effect of the BY list on the two duplicate scenarios")
    for scen in ("S14", "S17"):
        for label in ("template", "extended"):
            d = res[label][scen]
            print("  %-5s %-9s %d replacement rows -> %d keys%s"
                  % (scen, label, d["n_rp_raw"], d["n_dedup"],
                     "   [load refused]" if d["load_refused"] else ""))
    summary["f3"] = {
        "template": {k: list(map(str, v)) for k, v in
                     s14_order_test(("scn_num", "kit_num")).items()},
        "extended": {k: list(map(str, v)) for k, v in
                     s14_order_test(("scn_num", "kit_num", "kitnumrp",
                                     "lot_num", "btch_num")).items()},
    }

    print()
    print("=" * 78)
    print("F5  refid capacity under length $200")
    print("=" * 78)
    cap = refid_capacity()
    print("%-7s %-8s %-10s %-6s %s"
          % ("digits", "fit", "refid_len", "trunc", "formula floor(202/(w+2))"))
    for c in cap:
        print("%-7d %-8d %-10d %-6s %d"
              % (c["width"], c["whole_entries"], c["refid_len"],
                 c["truncated"], c["formula"]))
    summary["f5"] = cap

    print()
    print("=" * 78)
    print("F4  cardinality of the collapsed record")
    print("=" * 78)
    card = cardinality_case()
    print("visit carrying %d kits -> refid holds %d complete numbers + %d fragment "
          "(%d chars); ECLOT=%s, BATCHNUM=%s (kit %d)"
          % (card["kits_in_visit"], card["refid_complete"], card["refid_fragment"],
             card["refid_len"], card["eclot"], card["batchnum"],
             card["eclot_belongs_to_kit"]))
    summary["f4"] = card

    print()
    print("=" * 78)
    print("F6  visit vocabulary on the two sides of the join")
    print("=" * 78)
    j = s16_join_case()
    for c in j:
        print("%-18s irt-> %-18s crf-> %-18s %s"
              % (c["label"], c["irt_side"], c["crf_side"], c["join"]))
    summary["f6"] = j

    print()
    print("=" * 78)
    print("S15 volume   /   S13 structural")
    print("=" * 78)
    vol = volume_case()
    print("S15 %(visits)d visits, %(replacement_rows)d replacement rows, "
          "%(entries_loaded)d hash entries, %(probes_per_row)d probes/row, "
          "correct %(correct)d/%(visits)d, budget exhausted %(budget_exhausted)d"
          % vol)
    s13 = structure_case_s13()
    print("S13 rows reaching the visit-level feed: %d (expected 0); "
          "replacement rows: %d" % (s13["rows_in_feed"], s13["rows_in_rp"]))
    summary["s15"] = vol
    summary["s13"] = s13

    print()
    print("=" * 78)
    print("REGRESSION GATE")
    print("=" * 78)
    checks = []

    def chk(name, cond, detail=""):
        checks.append((name, bool(cond), detail))
        print("%-58s %s %s" % (name, "PASS" if cond else "FAIL", detail))

    chk("model reproduces all published rows", not failures)

    t = res["template"]
    chk("S05 dangling on hop 1 -> kit restored",
        (t["S05"]["rows"][0]["kit_num"] == 1001
         and t["S05"]["rows"][0]["lot_num"] == "LOT-A"
         and t["S05"]["rows"][0]["chain_status"] == "DANGLING"),
        "%s/%s" % (t["S05"]["rows"][0]["kit_num"], t["S05"]["rows"][0]["lot_num"]))
    chk("S06 dangling mid-chain -> kit restored to hop-2 kit",
        (t["S06"]["rows"][0]["kit_num"] == 1002
         and t["S06"]["rows"][0]["lot_num"] == "LOT-B"
         and t["S06"]["rows"][0]["chain_status"] == "DANGLING"))
    chk("S07 two-node cycle -> UNRESOLVED",
        t["S07"]["rows"][0]["chain_status"] == "UNRESOLVED")
    chk("S08 self-loop -> UNRESOLVED",
        t["S08"]["rows"][0]["chain_status"] == "UNRESOLVED")
    chk("S10 empty lookup table -> DANGLING, kit restored",
        (t["S10"]["rows"][0]["kit_num"] == 1001
         and t["S10"]["rows"][0]["chain_status"] == "DANGLING"))
    chk("every DANGLING/UNRESOLVED row emits a diagnostic",
        all(r["diagnostics"] >= 1 for s in ("S05", "S06", "S07", "S08", "S10")
            for r in t[s]["rows"]))
    chk("every RESOLVED row emits none",
        all(r["diagnostics"] == 0 for s in order for r in t[s]["rows"]
            if r["chain_status"] == "RESOLVED"))
    orig = {}
    for s in order:
        if s not in ("S13",):
            rows_o, _ = run_scenario(parse_raw(RAW), s, False,
                                     ("scn_num", "kit_num"))
            orig[s] = rows_o[0]["diagnostics"] if rows_o else None
    chk("original listing: CAUTION on the three dangling rows, silence on the cycles",
        all(orig[s] == 1 for s in ("S05", "S06", "S10"))
        and all(orig[s] == 0 for s in ("S07", "S08")))

    o_tpl = s14_order_test(("scn_num", "kit_num"))
    chk("F3 template dedup is still order dependent",
        o_tpl["as given"][0] != o_tpl["swapped"][0],
        "1003 vs 1004")
    o_ext = s14_order_test(("scn_num", "kit_num", "kitnumrp",
                            "lot_num", "btch_num"))
    chk("F3 extended dedup refuses the conflict",
        o_ext["as given"][0] == "REFUSED" and o_ext["swapped"][0] == "REFUSED")
    chk("S17 byte-identical replacement rows still collapse",
        (res["extended"]["S17"]["rows"][0]["kit_num"] == 1003
         and res["extended"]["S17"]["rows"][0]["chain_status"] == "RESOLVED"
         and res["extended"]["S17"]["load"]["entries"] == 2),
        "%d replacement rows -> %d keys"
        % (res["extended"]["S17"]["n_rp_raw"],
           res["extended"]["S17"]["n_dedup"]))
    chk("S17 gives the same answer under both dedup rules",
        res["template"]["S17"]["rows"][0]["kit_num"] == 1003
        and res["extended"]["S17"]["rows"][0]["kit_num"] == 1003,
        "the wider BY list only changes the outcome for conflicts")

    chk("F5 measured capacity matches floor(202/(w+2))",
        all(c["whole_entries"] == c["formula"] for c in cap),
        ",".join("%d:%d" % (c["width"], c["whole_entries"]) for c in cap))
    chk("S15 all rows land on the terminal kit",
        vol["correct"] == vol["visits"] and vol["budget_exhausted"] == 0)
    chk("S13 no kit_tyds row never reaches the feed", s13["rows_in_feed"] == 0)
    chk("F6 DISCONTINUED still misses the join",
        next(c for c in j if c["label"] == "DISCONTINUED")["join"] == "MISS")

    npass = sum(1 for _, ok, _ in checks if ok)
    print("\n%d checks, %d pass, %d fail"
          % (len(checks), npass, len(checks) - npass))
    summary["checks"] = [{"name": n, "pass": ok, "detail": d} for n, ok, d in checks]
    summary["totals"] = {"checks": len(checks), "pass": npass,
                         "fail": len(checks) - npass}

    if as_json:
        with open("ec_chain_verify.json", "w", encoding="utf-8") as fh:
            json.dump(summary, fh, indent=2, default=str)
        print("\nJSON summary written to ec_chain_verify.json")

    return 0 if npass == len(checks) else 1


if __name__ == "__main__":
    sys.exit(main())

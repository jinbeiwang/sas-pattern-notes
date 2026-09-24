#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
prompt_corpus_metrics.py — measure an archive of shipped agent system prompts.

Every number printed in agent-system-prompt-note.html comes from this file. Nothing is typed by
hand into the note; the note's tables are rendered from this script's output at build time.

The archive is not in this repository.  Point --corpus at a checkout of the public archive of
collected prompts (see the note's section 7 for the URL and the commit it was measured at).

    python prompt_corpus_metrics.py --corpus /path/to/corpus --out metrics.json

Output is deterministic: same archive commit in, byte-identical JSON out.
"""

import argparse
import io
import itertools
import json
import os
import re
import sys

# --------------------------------------------------------------------------------------------
# The case set.  Eighteen shipped prompts, chosen so that each structural family and each
# product surface (terminal CLI, IDE plugin, editor, browser agent, app builder) is represented
# at least once.  Paths are relative to the archive root.
# --------------------------------------------------------------------------------------------
CASES = [
    ("Claude Code",         "Anthropic/Claude Code/Prompt.txt"),
    ("Cursor Agent",        "Cursor Prompts/Agent Prompt 2025-09-03.txt"),
    ("Devin",               "Devin AI/Prompt.txt"),
    ("Manus",               "Manus Agent Tools & Prompt/Prompt.txt"),
    ("Replit Agent",        "Replit/Prompt.txt"),
    ("v0",                  "v0 Prompts and Tools/Prompt.txt"),
    ("Windsurf",            "Windsurf/Prompt Wave 11.txt"),
    ("Lovable",             "Lovable/Agent Prompt.txt"),
    ("Warp",                "Warp.dev/Prompt.txt"),
    ("GitHub Copilot (VS Code)", "VSCode Agent/Prompt.txt"),
    ("Codex CLI",           "Open Source prompts/Codex CLI/Prompt.txt"),
    ("Gemini CLI",          "Open Source prompts/Gemini CLI/google-gemini-cli-system-prompt.txt"),
    ("Cline",               "Open Source prompts/Cline/Prompt.txt"),
    ("RooCode",             "Open Source prompts/RooCode/Prompt.txt"),
    ("Bolt",                "Open Source prompts/Bolt/Prompt.txt"),
    ("Perplexity",          "Perplexity/Prompt.txt"),
    ("Kiro",                "Kiro/Vibe_Prompt.txt"),
    ("Trae Builder",        "Trae/Builder Prompt.txt"),
]

# Two extra files, quoted as evidence for the browser-agent comparison but not part of the
# eighteen: the injection-defence surface is only visible on browser agents.
EXTRA = [
    ("Claude for Chrome",   "Anthropic/Claude for Chrome/Prompt.txt"),
    ("Comet",               "Comet Assistant/System Prompt.txt"),
]

# --------------------------------------------------------------------------------------------
# Lexical probes.  Each is a literal or a word-boundary regex; counts are what the note reports.
# --------------------------------------------------------------------------------------------
MARKERS = [
    ("NEVER",     r"\bNEVER\b"),
    ("ALWAYS",    r"\bALWAYS\b"),
    ("MUST",      r"\bMUST\b"),
    ("IMPORTANT", r"\bIMPORTANT\b"),
    ("CRITICAL",  r"\bCRITICAL\b"),
]

AXES = [
    ("parallel",      r"\bparallel\b|simultaneous"),
    ("single_tool",   r"one tool at a time|one tool call per iteration|one tool per (?:message|turn)"),
    ("permission",    r"\bapprov|confirmation dialog|requires_approval"),
    ("plan_or_todo",  r"\btodo\b|task list|\bplanning\b"),
    ("memory",        r"\bmemory\b|persist across|remember across"),
    ("citation",      r"citation|\bcite\b|\[web:"),
    ("sandbox",       r"\bsandbox"),
    ("self_check",    r"self-correct|\bverify:|assert(?:ion)?\b"),
]

# A sentence travelling across product lines is the clearest evidence of a shared template.  These
# four were selected because a first pass over the whole archive showed they recur; the counts and
# the file lists below are the measurement, not the reason for the choice.
SIGNATURE = [
    ("completely resolved",                 "turn persistence"),
    ("mimic code style",                    "code-convention mimicry"),
    ("follow microsoft content policies",   "vendor policy delegation"),
    ("i can't assist with that",            "scripted refusal string"),
]

WORD_SIG = "completely resolved"


# --------------------------------------------------------------------------------------------
def read(path):
    return io.open(path, encoding="utf-8", errors="replace").read()


def norm_words(s):
    return re.sub(r"\s+", " ", s).strip().lower().split()


def measure(rel):
    p = rel
    raw = io.open(p, "rb").read()
    s = read(p)
    body = s
    lines = body.splitlines()
    nonblank = [l for l in lines if l.strip()]
    tag_sections = re.findall(r"(?m)^\s*<([a-zA-Z][\w-]*)[ >]", body)
    keep = [t for t in tag_sections
            if t.lower() not in ("example", "examples", "content", "command", "arguments",
                                 "div", "html", "body", "parameter", "parameter1_name",
                                 "parameter2_name", "tool_name", "path", "result", "old_str",
                                 "new_str", "insert", "remove_str", "diff", "regex")]
    row = {
        "bytes": len(raw),
        "chars": len(body),
        "lines": len(lines),
        "nonblank": len(nonblank),
        "ktok_est": round(len(body) / 4 / 1000.0, 1),
        "md_headings": len(re.findall(r"(?m)^#{1,4} ", body)),
        "tag_sections": len(keep),
        "bullets": len(re.findall(r"(?m)^\s*(?:[-*]|\d+\.)\s+", body)),
        "caps_tokens": len(re.findall(r"\b[A-Z]{3,}\b", body)),
    }
    for label, pat in MARKERS:
        row[label] = len(re.findall(pat, body))
    row["shout"] = row["NEVER"] + row["ALWAYS"] + row["MUST"] + row["IMPORTANT"] + row["CRITICAL"]
    row["shout_per_k"] = round(row["shout"] / (len(body) / 1000.0), 2)
    for label, pat in AXES:
        row[label] = len(re.findall(pat, body, re.I))
    return row


def shingles(words, width):
    return set(tuple(words[i:i + width]) for i in range(max(0, len(words) - width + 1)))


def longest_run(a, b, minw=8, cap=400):
    """Longest run of consecutive shared words between two token lists."""
    idx = {}
    for i in range(len(b) - minw + 1):
        idx.setdefault(tuple(b[i:i + minw]), []).append(i)
    best, bi = 0, 0
    i = 0
    while i <= len(a) - minw:
        key = tuple(a[i:i + minw])
        if key in idx:
            for j in idx[key]:
                n = 0
                while i + n < len(a) and j + n < len(b) and a[i + n] == b[j + n]:
                    n += 1
                if n > best:
                    best, bi = n, i
        i += 1
    return best, " ".join(a[bi:bi + min(best, cap)])


# --------------------------------------------------------------------------------------------
# The scan is scoped to the product directories the note reasons about, so that every row in
# every table has a product the reader has seen named.  Directories outside this list are not
# measured and no claim is made about them.
SCOPE_DIRS = (
    "Anthropic",
    "Comet Assistant",
    "Cursor Prompts",
    "Devin AI",
    "Google",
    "Kiro",
    "Lovable",
    "Manus Agent Tools & Prompt",
    "Open Source prompts",
    "Perplexity",
    "Replit",
    "Same.dev",
    "Trae",
    "v0 Prompts and Tools",
    "VSCode Agent",
    "Warp.dev",
    "Windsurf",
)


def product_of(rel):
    """The product a file belongs to, for evidence counts that must not double-count a vendor.

    Two directories in the archive are catch-alls holding several products; splitting on the
    second path component is what keeps 'four Cursor files' from reading as four vendors.
    """
    parts = rel.split("/")
    if parts[0] == "Open Source prompts" and len(parts) > 2:
        return parts[1]
    return parts[0]


def collect(corpus):
    files = []
    for d in SCOPE_DIRS:
        base = os.path.join(corpus, d)
        if not os.path.isdir(base):
            continue
        for dp, dn, fn in os.walk(base):
            for f in fn:
                if f.lower().endswith((".txt", ".md")):
                    rel = os.path.relpath(os.path.join(dp, f), corpus).replace("\\", "/")
                    if rel in ("README.md", "LICENSE.md"):
                        continue
                    if len(read(os.path.join(corpus, rel))) < 240:      # fragments, not prompts
                        continue
                    files.append(rel)
    return sorted(files)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", required=True)
    ap.add_argument("--out", default="metrics.json")
    ap.add_argument("--fragments", default="fragments.json",
                    help="write rendered HTML table bodies here (used by the build script)")
    args = ap.parse_args()

    C = args.corpus
    errors = []

    # ---- scope: how big is the archive -------------------------------------------------------
    all_files = collect(C)
    product_dirs = sorted(SCOPE_DIRS)
    scope = {"files": len(all_files), "products": len(product_dirs)}

    # ---- per-case structural measurement -----------------------------------------------------
    rows = {}
    for name, rel in CASES:
        p = os.path.join(C, rel)
        if not os.path.exists(p):
            errors.append("missing case file: " + rel)
            continue
        rows[name] = measure(p)

    # ---- signature sentences across the whole archive ----------------------------------------
    corpus_text = {rel: read(os.path.join(C, rel)).lower() for rel in all_files}
    signature = []
    for phrase, meaning in SIGNATURE:
        hits = [rel for rel in all_files if phrase in corpus_text[rel]]
        products = sorted(set(product_of(rel) for rel in hits))
        signature.append({"phrase": phrase, "meaning": meaning,
                          "files": len(hits), "products": products,
                          "n_products": len(products), "paths": hits})

    # ---- near-duplicate families over the whole archive ---------------------------------------
    words = {rel: norm_words(read(os.path.join(C, rel))) for rel in all_files}
    sh = {rel: shingles(words[rel], 12) for rel in all_files}
    # A containment ratio alone is misleading on short files: two 300-word fragments can share
    # 20 shingles out of 25 and score 0.8.  Require an absolute overlap as well.
    edges = []
    for a, b in itertools.combinations(all_files, 2):
        inter = len(sh[a] & sh[b])
        if inter < 100:
            continue
        cont = inter / float(min(len(sh[a]), len(sh[b])))
        if cont >= 0.15:
            n, run = longest_run(words[a], words[b])
            edges.append({"a": a, "b": b, "containment": round(cont, 3),
                          "shared": inter, "run_words": n, "run": run})
    edges.sort(key=lambda p: -p["containment"])

    # Families: connected components of the strongly-similar sub-graph, so that sixteen pairwise
    # rows inside one vendor collapse into the single fact they represent.
    parent = {f: f for f in all_files}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    strong = [e for e in edges if e["containment"] >= 0.30]
    for e in strong:
        ra, rb = find(e["a"]), find(e["b"])
        if ra != rb:
            parent[ra] = rb
    groups = {}
    for e in strong:
        groups.setdefault(find(e["a"]), set()).update((e["a"], e["b"]))
    families = []
    for root, members in groups.items():
        inner = [e for e in strong if e["a"] in members and e["b"] in members]
        families.append({
            "members": sorted(members),
            "n_files": len(members),
            "n_pairs": len(inner),
            "max_containment": max(e["containment"] for e in inner),
            "max_run": max(e["run_words"] for e in inner),
            "products": sorted(set(product_of(m) for m in members)),
        })
    families.sort(key=lambda f: (-f["n_files"], -f["max_containment"]))

    # Cross-product pairs: the evidence that a paragraph travelled between vendors.  Same-vendor
    # pairs are already summarised by the family row above.
    cross = [e for e in edges if product_of(e["a"]) != product_of(e["b"])]

    # ---- two similarity measures that disagree ------------------------------------------------
    # The tag vocabulary and the running text answer different questions.  This pair is the
    # worked example the note uses: structurally alike, textually unrelated.
    def tag_jaccard(rel_a, rel_b):
        def tags(r):
            return set(re.findall(r"(?m)^\s*<([a-zA-Z][\w-]*)[ >]",
                                  read(os.path.join(C, r))))
        A, B = tags(rel_a), tags(rel_b)
        return len(A & B) / float(len(A | B)) if (A | B) else 0.0

    comparable = [("Claude Code", "Anthropic/Claude Code/Prompt.txt"),
                  ("Gemini CLI", "Open Source prompts/Gemini CLI/google-gemini-cli-system-prompt.txt"),
                  ("Cline", "Open Source prompts/Cline/Prompt.txt"),
                  ("RooCode", "Open Source prompts/RooCode/Prompt.txt")]
    disagreement = []
    for (na, ra), (nb, rb) in itertools.combinations(comparable, 2):
        inter = len(sh[ra] & sh[rb])
        disagreement.append({
            "a": na, "b": nb,
            "tag_jaccard": round(tag_jaccard(ra, rb), 3),
            "tag_kinds": len(set(re.findall(r"(?m)^\s*<([a-zA-Z][\w-]*)[ >]", read(os.path.join(C, ra))))),
            "shingle_containment": round(inter / float(min(len(sh[ra]), len(sh[rb]))), 3),
            "shared_shingles": inter,
            "longest_run": longest_run(words[ra], words[rb])[0],
        })

    out = {
        "scope": scope,
        "cases": [{"name": n, "path": rel, **rows[n]} for n, rel in CASES if n in rows],
        "signature": signature,
        "families": families,
        "cross_pairs": cross[:14],
        "disagreement": disagreement,
    }

    # ---- numbers quoted in prose -------------------------------------------------------------
    # Anything the note states in a sentence rather than in a table comes from here, so a
    # sentence cannot drift away from the measurement it cites.
    sig = {s["phrase"]: s for s in signature}

    def sig_n(phrase, key):
        return sig[phrase][key]

    numbers = {
        "scope_files": scope["files"],
        "scope_products": scope["products"],
        "n_cases": len(out["cases"]),
        "chars_min": "{:,}".format(min(c["chars"] for c in out["cases"])),
        "chars_max": "{:,}".format(max(c["chars"] for c in out["cases"])),
        "chars_max_case": max(out["cases"], key=lambda c: c["chars"])["name"],
        "pure_prose_case": next((c["name"] for c in out["cases"]
                                 if c["md_headings"] == 0 and c["tag_sections"] == 0), "-"),
        "never_max_case": max(out["cases"], key=lambda c: c["NEVER"])["name"],
        "never_max": max(c["NEVER"] for c in out["cases"]),
        "chars_ratio": "%.1f" % (max(c["chars"] for c in out["cases"]) /
                                 float(min(c["chars"] for c in out["cases"]))),
        "tok_max": "%.1f" % max(c["ktok_est"] for c in out["cases"]),
        "shout_min": "%.2f" % min(c["shout_per_k"] for c in out["cases"]),
        "shout_max": "%.2f" % max(c["shout_per_k"] for c in out["cases"]),
        "shout_max_case": max(out["cases"], key=lambda c: c["shout_per_k"])["name"],
        "shout_min_case": min(out["cases"], key=lambda c: c["shout_per_k"])["name"],
        "shout_zero": sum(1 for c in out["cases"] if c["shout_per_k"] == 0),
        "parallel_zero": sum(1 for c in out["cases"] if c["parallel"] == 0),
        "parallel_max_case": max(out["cases"], key=lambda c: c["parallel"])["name"],
        "parallel_max": max(c["parallel"] for c in out["cases"]),
        "single_tool_cases": ", ".join(c["name"] for c in out["cases"] if c["single_tool"]),
        "no_md_no_tag": sum(1 for c in out["cases"]
                            if c["md_headings"] == 0 and c["tag_sections"] == 0),
        "xml_cases": sum(1 for c in out["cases"] if c["tag_sections"] >= 5),
        "md_cases": sum(1 for c in out["cases"] if c["md_headings"] >= 5),
        "sig_resolved_files": sig_n("completely resolved", "files"),
        "sig_resolved_products": sig_n("completely resolved", "n_products"),
        "sig_resolved_list": ", ".join(sig_n("completely resolved", "products")),
        "sig_mimic_files": sig_n("mimic code style", "files"),
        "sig_mimic_products": sig_n("mimic code style", "n_products"),
        "sig_policy_files": sig_n("follow microsoft content policies", "files"),
        "sig_policy_products": sig_n("follow microsoft content policies", "n_products"),
        "sig_refusal_files": sig_n("i can't assist with that", "files"),
        "sig_refusal_products": sig_n("i can't assist with that", "n_products"),
        "family_count": len(families),
        "cross_count": len(cross),
        "vsc_files": next((f["n_files"] for f in families if f["products"] == ["VSCode Agent"]), 0),
        "vsc_pairs": next((f["n_pairs"] for f in families if f["products"] == ["VSCode Agent"]), 0),
        "vsc_max_containment": "%.3f" % next((f["max_containment"] for f in families
                                              if f["products"] == ["VSCode Agent"]), 0.0),
    }
    for e in cross:
        key = "cross_%s_%s" % (re.sub(r"\W+", "_", product_of(e["a"])).strip("_"),
                               re.sub(r"\W+", "_", product_of(e["b"])).strip("_"))
        numbers[key + "_containment"] = "%.3f" % e["containment"]
        numbers[key + "_run"] = e["run_words"]
    # How far apart one product's own released versions drift: a hint at how fast the text is
    # rewritten.  Scoped to the editor agent (the CLI surface is a separate, shorter prompt).
    def version_spread(prefix):
        group = [rel for rel in all_files if rel.startswith(prefix)]
        vals = []
        for a, b in itertools.combinations(group, 2):
            vals.append(len(sh[a] & sh[b]) / float(min(len(sh[a]), len(sh[b]))))
        return group, (min(vals) if vals else 0.0), (max(vals) if vals else 0.0)

    group, lo, hi = version_spread("Cursor Prompts/Agent Prompt")
    numbers["cursor_agent_files"] = len(group)
    numbers["cursor_agent_cont_min"] = "%.2f" % lo
    numbers["cursor_agent_cont_max"] = "%.2f" % hi

    for e in disagreement:
        numbers["dis_%s_%s_tagj" % (re.sub(r"\W+", "_", e["a"]), re.sub(r"\W+", "_", e["b"]))] = "%.2f" % e["tag_jaccard"]
        numbers["dis_%s_%s_cont" % (re.sub(r"\W+", "_", e["a"]), re.sub(r"\W+", "_", e["b"]))] = "%.3f" % e["shingle_containment"]
        numbers["dis_%s_%s_run" % (re.sub(r"\W+", "_", e["a"]), re.sub(r"\W+", "_", e["b"]))] = e["longest_run"]
    out["numbers"] = numbers

    io.open(args.out, "w", encoding="utf-8").write(
        json.dumps(out, ensure_ascii=False, indent=1))

    # ---- rendered fragments ------------------------------------------------------------------
    def esc(t):
        return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    fa = []
    for r in out["cases"]:
        fa.append("<tr><td>{}</td><td class=\"num\">{:,}</td><td class=\"num\">{:,}</td>"
                  "<td class=\"num\">{}</td><td class=\"num\">{}</td><td class=\"num\">{}</td></tr>"
                  .format(r["name"], r["chars"], r["nonblank"], r["md_headings"],
                          r["tag_sections"], r["bullets"]))

    fb = []
    for r in sorted(out["cases"], key=lambda x: -x["shout_per_k"]):
        fb.append("<tr><td>{}</td><td class=\"num\">{}</td><td class=\"num\">{}</td>"
                  "<td class=\"num\">{}</td><td class=\"num\">{}</td><td class=\"num\">{}</td>"
                  "<td class=\"num\">{:.2f}</td></tr>"
                  .format(r["name"], r["NEVER"], r["ALWAYS"], r["MUST"], r["IMPORTANT"],
                          r["CRITICAL"], r["shout_per_k"]))

    fc = []
    for r in out["cases"]:
        def cell(v):
            return "<td class=\"num\">{}</td>".format(v if v else "&middot;")
        fc.append("<tr><td>{}</td>{}{}{}{}{}{}{}</tr>".format(
            r["name"], cell(r["parallel"]), cell(r["single_tool"]), cell(r["permission"]),
            cell(r["plan_or_todo"]), cell(r["memory"]), cell(r["citation"]), cell(r["sandbox"])))

    fd = []
    for s in out["signature"]:
        fd.append("<tr><td><code>{}</code></td><td class=\"num\">{}</td><td class=\"num\">{}</td>"
                  "<td>{}</td></tr>".format(esc(s["phrase"]), s["files"], s["n_products"],
                                            esc(", ".join(s["products"]))))

    fe = []
    for f in out["families"]:
        sample = ", ".join(f["members"][:3])
        if f["n_files"] > 3:
            sample += ", …"
        fe.append("<tr><td class=\"num\">{}</td><td class=\"num\">{}</td>"
                  "<td><span class=\"num\">{:.3f}</span></td><td class=\"num\">{:,}</td>"
                  "<td>{}</td></tr>".format(f["n_files"], f["n_pairs"], f["max_containment"],
                                            f["max_run"], esc(sample)))

    ff = []
    for p in out["cross_pairs"]:
        ff.append("<tr><td><span class=\"num\">{:.3f}</span></td><td><span class=\"num\">{:,}</span></td>"
                  "<td><span class=\"num\">{}</span></td><td>{} &harr; {}</td></tr>"
                  .format(p["containment"], p["shared"], p["run_words"], esc(p["a"]), esc(p["b"])))

    frag = {"table_scale": "\n".join(fa), "table_shout": "\n".join(fb),
            "table_axes": "\n".join(fc), "table_signature": "\n".join(fd),
            "table_families": "\n".join(fe), "table_cross": "\n".join(ff)}
    io.open(args.fragments, "w", encoding="utf-8").write(
        json.dumps(frag, ensure_ascii=False, indent=1))

    if errors:
        for e in errors:
            sys.stderr.write("ERROR " + e + "\n")
        return 1
    sys.stdout.write("cases=%d archive_files=%d product_dirs=%d families=%d cross_pairs=%d\n"
                     % (len(out["cases"]), scope["files"], scope["products"],
                        len(families), len(cross)))
    return 0


if __name__ == "__main__":
    sys.exit(main())

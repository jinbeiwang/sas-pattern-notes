# SAS Pattern Notes

**Live site — <https://jinbeiwang.github.io/sas-pattern-notes/>**

De-identified, reusable write-ups of coding patterns from clinical statistical programming. Each note is a
single self-contained HTML file — no font CDN, no script CDN, no image files, nothing to install. Read it on
the live site above, or open the file straight from the repository.

Every note answers the same seven questions, in the same order:

1. What the code has to do — the requirement, then the data shape that follows from it
2. Background worth stating — only the machinery the listing below depends on
3. Reading the code — the listing, annotated by step
4. Why this approach and not the obvious one — the comparison, then the argument
5. Behaviour under imperfect input — what it gets right, and what it silently gets wrong
6. Reuse checklist — what to change, what to check before it goes into another program
7. Verification report — what was executed, the data each case is built from, every run quoted in full, and
   the few behaviours that were assumed rather than observed

The table of contents is generated from the headings when the page loads and lives in a panel on the left
that can be hidden. Adding or renaming a section needs no edit to any link list.

## Notes

Each note except the first is served under the site root at its own filename, for example
<https://jinbeiwang.github.io/sas-pattern-notes/sas-hash-clinical-note.html>.

| Note | Read online | Subject |
|---|---|---|
| The SAS hash object: definition, lookup, load and output | [web](https://jinbeiwang.github.io/sas-pattern-notes/sas-hash-clinical-note.html) · [source](sas-hash-clinical-note.html) | Full syntax skeleton (declare → definekey → definedata → definedone → find / output), six argument tags, the method set and its return codes; four clinical shapes (screening and population flags, horizontal ADSL→ADLB merge, cross-visit baseline retrieval, AE×CM many-to-many), written in Chinese. Eight pitfalls with sources — duplicate keys kept silently, dataset loaded at `definedone()` rather than `declare`, data variables retaining their previous value when `find()` misses, `output()` not writing keys, `key:` type agreement. |
| Chained kit replacement with the SAS hash object | [web](https://jinbeiwang.github.io/sas-pattern-notes/) · [source](index.html) | Resolving a replacement chain of unknown depth in a single pass of a DATA step; why an in-memory hash and not a merge; seventeen scenarios of imperfect input, executed against a reference model of the step, and the six defects they expose — including the one that survives the obvious fix, where `duplicate: "error"` turns out to be inert as long as the deduplication upstream still hides the conflict. |

## Reference model

`reference-model/` holds three dependency-free Python 3 scripts, written for the last note and runnable
without SAS. Together they carry the three claims that note's section 7 makes.

| Script | Command | What it settles |
|---|---|---|
| `ec_chain_verify.py` | `python ec_chain_verify.py` | Seventeen scenarios against the original listing, the hardened one, and the same hardened code under its previous `by` list. Each case is deterministic; nothing is randomised or seeded. Exits non-zero if any of the seventeen gate checks fails. `--cases` prints the dummy data catalogue on its own, `--json` also writes the JSON summary. |
| `code_fidelity.py` | `python code_fidelity.py` | Whether the code printed in the note is the code in the program. Strips the markup out of the note's listings, removes comments, folds case, collapses whitespace — leaving string literals alone, so `', '` is not read as `','` — and compares statement by statement. Then reports what the hardening consists of, as two explicit lists rather than as prose. |
| `check_recorded_runs.py` | `python check_recorded_runs.py` | Whether the runs quoted in the note are still live. Re-executes the other two, strips the markup out of each quoted block and compares the two byte for byte. Run this after any edit to a script or to section 7: a run quoted in a note stops being evidence the moment it stops being reproducible. |

`code_fidelity.py` takes `--sas path/to/program.sas` because the program it checks is not in this
repository; the other two take `--note` if the note is not where they expect it.

They exist because SAS is not always available to the person writing the note, and "the reasoning is sound" is
a weaker claim than "here is the run, and here is how to get it again".

## Conventions

- Study and protocol numbers are replaced by a placeholder such as `NNNN`; library names, file paths, program
  headers, author names and input dataset names are removed or generalised.
- Listings are annotated by step and by in-code marker (`(1)`, `(2)`) rather than by line number, so a listing
  can be lifted into another program without invalidating every reference to it.
- Behaviour attributed to the language rather than observed in the code is cited to the vendor documentation.
- Where the analysis was static — no SAS session available — the note says so, in the masthead and in the
  footer, instead of implying that it was measured. Where the logic could be executed without SAS, the note
  reports the executable model, quotes its output, and states which few behaviours the model had to assume
  rather than observe.
- Every behaviour the note claims is traceable to something a reader can re-run: a documented statement, a
  published paper, a scenario identifier, or the harness in `reference-model/`.

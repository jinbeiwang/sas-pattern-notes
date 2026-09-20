# SAS Pattern Notes

**Live site — <https://jinbeiwang.github.io/sas-pattern-notes/>**

De-identified, reusable write-ups of coding patterns from clinical statistical programming. Each note is a
single self-contained HTML file — no font CDN, no script CDN, no image files, nothing to install. Read it on
the live site above, or open the file straight from the repository.

Every note answers the same seven questions, in the same order:

1. What the code has to do — the requirement, then the data shape that follows from it
2. Background worth stating — only the machinery the listing below depends on
3. Reading the code — the current listing, annotated by step
4. Why this approach and not the obvious one — the comparison, then the argument
5. Design and correctness — what it guarantees, a scenario matrix, and the defects it does not fix
6. Reuse checklist — what to change, what to check before it goes into another program
7. The check that ships with the note — what it asserts, the dummy data behind every case, and what it does
   not settle

The table of contents is generated from the headings when the page loads and lives in a panel on the left
that can be hidden. Adding or renaming a section needs no edit to any link list.

## Notes

Each note except the first is served under the site root at its own filename, for example
<https://jinbeiwang.github.io/sas-pattern-notes/sas-hash-clinical-note.html>.

| Note | Read online | Subject |
|---|---|---|
| The SAS hash object: definition, lookup, load and output | [web](https://jinbeiwang.github.io/sas-pattern-notes/sas-hash-clinical-note.html) · [source](sas-hash-clinical-note.html) | Full syntax skeleton (declare → definekey → definedata → definedone → find / output), six argument tags, the method set and its return codes; four clinical shapes (screening and population flags, horizontal ADSL→ADLB merge, cross-visit baseline retrieval, AE×CM many-to-many), written in Chinese. Eight pitfalls with sources — duplicate keys kept silently, dataset loaded at `definedone()` rather than `declare`, data variables retaining their previous value when `find()` misses, `output()` not writing keys, `key:` type agreement. |
| Chained kit replacement with the SAS hash object | [web](https://jinbeiwang.github.io/sas-pattern-notes/) · [source](index.html) | Resolving a replacement chain of unknown depth in a single pass of a DATA step; why an in-memory hash and not a merge; seventeen scenarios of imperfect input, checked by a self-contained Base SAS program that ships with the note. The duplicate rule is the part worth reading twice: `duplicate: "error"` only does its job because the deduplication in front of it carries the payload in its `by` list rather than the key alone. |

## Checks

Nothing in these notes is a transcript taken on trust. Each claim about a program is carried by something a
reader can re-run.

| File | Command | What it settles |
|---|---|---|
| `kit_chain_check.sas` | `sas kit_chain_check.sas` | Base SAS, no study macros and no external input. Builds seventeen scenarios as dummy data, runs the chain step over each one, and asserts the kit, lot, batch, status and probe count of every visit-level row. Prints one verdict per assertion and aborts on any failure. Written for the kit-replacement note, and the file the note's section 7 describes. |
| `reference-model/code_fidelity.py` | `python code_fidelity.py` | That the note describes the code it claims to describe. Compares the listings printed in the note, and the step inside `kit_chain_check.sas`, against the program, statement by statement — comments, case and whitespace ignored, string literals preserved so `', '` is not read as `','` — and the fixture printed in section 7 against the one in the verifier. Takes `--sas` because the program it checks is not in this repository. |
| `reference-model/ec_chain_verify.py` | `python ec_chain_verify.py` | Seventeen scenarios against a dependency-free emulation of the DATA step, for readers without SAS. Its own contribution is the counterfactual the SAS check cannot run: the same scenarios under a `by` list of the key alone, which is where the duplicate rule goes quiet. Exits non-zero if any gate check fails; `--cases` prints the dummy data catalogue on its own. |

## Conventions

- Study and protocol numbers are replaced by a placeholder such as `NNNN`; library names, file paths, program
  headers, author names and input dataset names are removed or generalised.
- Listings are annotated by step and by in-code marker (`(1)`, `(2)`) rather than by line number, so a listing
  can be lifted into another program without invalidating every reference to it.
- Behaviour attributed to the language rather than observed in the code is cited to the vendor documentation.
- A note documents the code **as it stands**. Where a pattern was hardened after the first note was written,
  the note describes the hardened step and argues for it; it does not keep the superseded listing as a
  foil, because the reader's job is to review what runs, not the road to it.
- Where SAS was not available to the person writing the note, the note says so in the masthead and in the
  footer, and ships a runnable check instead of quoting a transcript. The expected results are then the
  specification the check asserts, and the note says which behaviours only a real session can settle.
- Every behaviour the note claims is traceable to something a reader can re-run: a documented statement, a
  scenario identifier, or one of the checks above.

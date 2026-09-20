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
| Chained kit replacement with the SAS hash object | [web](https://jinbeiwang.github.io/sas-pattern-notes/) · [source](index.html) | Resolving a replacement chain of unknown depth in a single pass of a DATA step; why an in-memory hash and not a merge; twelve cases of imperfect input — a chain of three the longest, since that is the most any subject has shown — each one printed as dummy data and asserted by a self-contained Base SAS program that ships with the note. The duplicate rule is the part worth reading twice: `duplicate: "error"` only does its job because the deduplication in front of it carries the payload in its `by` list rather than the key alone. |

## Checks

Nothing in these notes is a transcript taken on trust. Each claim about a program is carried by something a
reader can re-run, and the checks are tied to the note rather than to a memory of it.

| File | Command | What it settles |
|---|---|---|
| `kit_chain_check.sas` | `sas kit_chain_check.sas` | Base SAS, no study macros and no external input. Builds every case of the note's scenario matrix as dummy data, runs the chain step over each one, and asserts the kit, lot, batch, status and probe count of every visit-level row — eleven assertions in all, plus the block that demonstrates the refused load. Prints one verdict per assertion and aborts on any failure. The file the note's section 7 describes. |
| `reference-model/code_fidelity.py` | `python code_fidelity.py` | That the note describes the code it claims to describe: the listings printed in section 3, and the step inside `kit_chain_check.sas`, against the program, statement by statement — comments, case and whitespace ignored, string literals preserved so `', '` is not read as `','`. It also holds section 7's fixture and every row of section 5's scenario matrix to the check's own fixture and expected table, so a number that drifts in the prose fails the build of the note. Takes `--sas` because the program it checks is not in this repository. |
| `reference-model/ec_step_model.py` | `python ec_step_model.py` | The same cases through a dependency-free emulation of the DATA step, for readers without SAS. It reads the fixture, the expected table and the volume parameters straight out of `kit_chain_check.sas`, so it cannot drift from the check, and it reproduces every expected row. Its own contribution is the counterfactual a SAS session would need two programs to show: the deduplication counts under both `by` lists, and the answer each of them produces when two rows disagree. Exits non-zero if any row or count fails. |

## Conventions

- Study and protocol numbers are replaced by a placeholder such as `NNNN`; library names, file paths, program
  headers, author names and input dataset names are removed or generalised.
- Listings are annotated by step and by in-code marker (`(1)`, `(2)`) rather than by line number, so a listing
  can be lifted into another program without invalidating every reference to it.
- Behaviour attributed to the language rather than observed in the code is cited to the vendor documentation.
- A note documents the code **as it stands**. Where a pattern was hardened after the first note was written,
  the note describes the hardened step and argues for it; it does not keep the superseded listing as a
  foil, because the reader's job is to review what runs, not the road to it.
- A case is in the scenario matrix only if the step under test is what decides its outcome. Input that is
  settled upstream — a screening row, a visit label the clinical side spells differently — is not a scenario
  here, however interesting it is; cases that turn out to be the same failure twice are dropped rather than
  kept for symmetry. Retiring a case means saying so in the note, so that a reader who met the old list knows
  what happened to it.
- Where SAS was not available to the person writing the note, the note says so in the masthead and in the
  footer, and ships a runnable check instead of quoting a transcript. The expected results are then the
  specification the check asserts, and the note says which behaviours only a real session can settle.
- Every behaviour the note claims is traceable to something a reader can re-run: a documented statement, a
  scenario identifier, or one of the checks above.

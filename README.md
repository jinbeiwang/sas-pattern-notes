# SAS Pattern Notes

**Live site — <https://jinbeiwang.github.io/sas-pattern-notes/>**

De-identified, reusable write-ups of coding patterns from clinical statistical programming. Each note is a
single self-contained HTML file — no font CDN, no script CDN, no image files, nothing to install. Read it on
the live site above, or open the file straight from the repository.

The chained kit-replacement note has been **retired from this repository**. It is published with the other notes
at <https://jinbeiwang.github.io/notes/sas-kit-chain-replacement.html>, and one note would not be maintained
in two places. The site root forwards there, so links into this repository keep working; the full text stays in
the history as `git show 21bc431:index.html`. The programs that note describes are still here — see Checks.

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

Each note is served under the site root at its own filename, for example
<https://jinbeiwang.github.io/sas-pattern-notes/sas-hash-clinical-note.html>.

| Note | Read online | Subject |
|---|---|---|
| MMRM for a longitudinal continuous endpoint | [web](https://jinbeiwang.github.io/sas-pattern-notes/mmrm-clinical-note.html) · [source](mmrm-clinical-note.html) | The primary analysis of a Phase III continuous endpoint measured at several visits: the marginal model (`PROC MIXED`, no `RANDOM` statement, `TYPE=UN`, `DDFM=KR`), why the baseline record must leave the response vector while its value stays as a covariate, what each covariance structure costs in parameters, why the read-out goes through `LSMEANS ... / SLICE=` rather than hand-written `ESTIMATE` coefficients, and the prespecification in the SAP that the model cannot supply for itself. Written in Chinese. Six defects with the input that triggers them, including the finding that a large minority of protocols still leave the covariance structure, the estimation method and the fallback unstated. |
| The SAS hash object: definition, lookup, load and output | [web](https://jinbeiwang.github.io/sas-pattern-notes/sas-hash-clinical-note.html) · [source](sas-hash-clinical-note.html) | Full syntax skeleton (declare → definekey → definedata → definedone → find / output), six argument tags, the method set and its return codes; four clinical shapes (screening and population flags, horizontal ADSL→ADLB merge, cross-visit baseline retrieval, AE×CM many-to-many), written in Chinese. Eight pitfalls with sources — duplicate keys kept silently, dataset loaded at `definedone()` rather than `declare`, data variables retaining their previous value when `find()` misses, `output()` not writing keys, `key:` type agreement. |
| Chained kit replacement with the SAS hash object | [web](https://jinbeiwang.github.io/notes/sas-kit-chain-replacement.html) · [source](https://github.com/jinbeiwang/jinbeiwang.github.io/blob/main/src/content/notes/sas-kit-chain-replacement.md) | Resolving a replacement chain of unknown depth in a single pass of a DATA step; why an in-memory hash and not a merge; twelve cases of imperfect input — a chain of three the longest, since that is the most any subject has shown — each one printed as dummy data and asserted by a self-contained Base SAS program that ships with the note. The duplicate rule is the part worth reading twice: `duplicate: "error"` only does its job because the deduplication in front of it carries the payload in its `by` list rather than the key alone. |

## Checks

Nothing in these notes is a transcript taken on trust. Each claim about a program is carried by something a
reader can re-run, and the checks are tied to the note rather than to a memory of it.

| File | Command | What it settles |
|---|---|---|
| [`kit_chain_check.sas`](kit_chain_check.sas) | `sas kit_chain_check.sas` | Base SAS, no study macros and no external input. Builds every case of the note's scenario matrix as dummy data, runs the chain step over each one, and asserts the kit, lot, batch, status and probe count of every visit-level row — eleven assertions in all, plus the block that demonstrates the refused load. Prints one verdict per assertion and aborts on any failure. The file the note's section 7 describes. |
| [`mmrm_check.sas`](mmrm_check.sas) | `sas mmrm_check.sas` | Base SAS plus SAS/STAT, no study macros and no external input. Builds a 240-subject, three-arm, five-visit fixture with monotone dropout as data, fits the note's model over it, and asserts seventeen structural claims — the parameter count of each covariance structure at K = 5, the Type 3 numerator degrees of freedom that prove `AVISITN` really is a classification variable, that the baseline record stayed out of the response vector, that Kenward-Roger moved the denominator degrees of freedom away from containment, and that the fixture really contains a subject with no response, a subject seen once and subjects who dropped out. Prints one verdict per assertion and aborts on any failure. A fragile block behind `RUN_FRAGILE` refits with the baseline record left in and prints what that costs; it is announced in the log and skippable, because its failure is the point. |
| [`reference-model/mmrm_fidelity.py`](reference-model/mmrm_fidelity.py) | `python mmrm_fidelity.py` | That the note describes the program it claims to describe: the two listings printed in section 3 appear in `mmrm_check.sas` as a contiguous run of statements — comments, case and whitespace ignored, string literals preserved by a content-keyed mask so `'Placebo'` cannot drift into something else — and every numeric value the check asserts is also stated in the note, so a number that drifts in the prose fails. Exits non-zero on any break. |
| [`reference-model/code_fidelity.py`](reference-model/code_fidelity.py) | `python code_fidelity.py` | That the note describes the code it claims to describe: the listings printed in section 3, and the step inside `kit_chain_check.sas`, against the program, statement by statement — comments, case and whitespace ignored, string literals preserved so `', '` is not read as `','`. It also holds section 7's fixture and every row of section 5's scenario matrix to the check's own fixture and expected table, so a number that drifts in the prose fails the build of the note. Takes `--sas` because the program it checks is not in this repository. |
| [`reference-model/ec_step_model.py`](reference-model/ec_step_model.py) | `python ec_step_model.py` | The same cases through a dependency-free emulation of the DATA step, for readers without SAS. It reads the fixture, the expected table and the volume parameters straight out of `kit_chain_check.sas`, so it cannot drift from the check, and it reproduces every expected row. Its own contribution is the counterfactual a SAS session would need two programs to show: the deduplication counts under both `by` lists, and the answer each of them produces when two rows disagree. Exits non-zero if any row or count fails. |

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

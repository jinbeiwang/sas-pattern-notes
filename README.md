# SAS Pattern Notes

De-identified, reusable write-ups of coding patterns from clinical statistical programming. Each note is a
single self-contained HTML file — no font CDN, no script CDN, no image files, nothing to install. Open it, or
serve the repository with GitHub Pages and read it there.

Every note answers the same six questions, in the same order:

1. What the code has to do — the requirement, then the data shape that follows from it
2. Background worth stating — only the machinery the listing below depends on
3. Reading the code — the listing, annotated by step
4. Why this approach and not the obvious one — the comparison, then the argument
5. Behaviour under imperfect input — what it gets right, and what it silently gets wrong
6. Reuse checklist — what to change, what to check before it goes into another program

The table of contents is generated from the headings when the page loads and lives in a panel on the left
that can be hidden. Adding or renaming a section needs no edit to any link list.

## Notes

| Note | Subject |
|---|---|
| [Chained kit replacement with the SAS hash object](index.html) | Resolving a replacement chain of unknown depth in a single pass of a DATA step; why an in-memory hash and not a merge; sixteen scenarios of imperfect input and the six real defects they expose. |

## Conventions

- Study and protocol numbers are replaced by a placeholder such as `NNNN`; library names, file paths, program
  headers, author names and input dataset names are removed or generalised.
- Listings are annotated by step and by in-code marker (`(1)`, `(2)`) rather than by line number, so a listing
  can be lifted into another program without invalidating every reference to it.
- Behaviour attributed to the language rather than observed in the code is cited to the vendor documentation.
- Where the analysis was static — no SAS session available — the note says so, in the masthead and in the
  footer, instead of implying that it was measured.

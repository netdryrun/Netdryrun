# Amendments

Changes to a pre-registered expected verdict, after the case files were first committed, with the reason and the evidence. Nothing here yet.

Before the first run, a fresh agent read the expected verdicts against the code (2026-10-30) and the cases were corrected in place, before any lab run, so these are corrections, not amendments: 01 match text; 02 weaker strings; 03 report search and a stated assumption; 04 a delayed effect; 05 an empty intent; 07 a runnable command; 08 a guard the 0.3.3 convergence gate does not block.

Rule: an expected verdict is never edited to make a run match. If a lab run shows an expectation was wrong, the change is listed here (case, old value, new value, the run that showed it, the date), the case's `live_verified` stays `false` until a rerun gives the new value, and `MANIFEST.sha256` is regenerated in the same commit.

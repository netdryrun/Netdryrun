# Amendments

Changes to a pre-registered expected verdict, after the case files were first committed, with the reason and the evidence. Nothing here yet.

Rule: an expected verdict is never edited to make a run match. If a lab run shows an expectation was wrong, the change is listed here (case, old value, new value, the run that showed it, the date), the case's `live_verified` stays `false` until a rerun gives the new value, and `MANIFEST.sha256` is regenerated in the same commit.

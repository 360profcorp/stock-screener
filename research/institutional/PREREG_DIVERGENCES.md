# PR #20 vs the owner's original PREREG_INSTITUTIONAL_AI.md

## Why there is a divergence
The owner's `PREREG_INSTITUTIONAL_AI.md`, `CLAUDE_TASK.md` and
`ai_institutional_intelligence_v1.zip` never reached the working session:
- the attachments arrived empty three times;
- on 2026-10-25 the session's upload folder held only two unrelated files from 2026-10-13.

`PREREG_INSTITUTIONAL.md` (commit c8c4c39) was therefore written from the owner's chat
instructions only, and says so at the top. It promised to log every difference once the
original arrived. The original has still not been seen, so the full list cannot be
produced. This note records what is known from the owner's message of 2026-10-25.

## Known divergence: the rating was not the original one
| | Original (owner, 2026-10-25) | Tested in PR #20 |
|---|---|---|
| Rating | **75 % RS + 25 % institutional evidence** (a weighted blend) | **lexicographic:** the institutional feature first, RS only to break ties (INS, BR); or the mean percentile of F1 and F2 with no RS weight (IR) |
| Effective RS weight | 75 % | about 0 % (F2 is continuous, so ties are rare and BR is in effect a pure F2 order); 0 % in IR |
| "Institutional evidence" | defined in the original (not seen) | F1 = distinct insiders with open-market purchases (90 days); F2 = 13F ownership-breadth change among filers present in both quarters |

**Consequences**
- PR #20 **did not test the original hypothesis.** Its results say nothing about a
  75 / 25 blend.
- A 75 % RS blend stays close to RS-first: it can only reorder candidates whose RS is close.
  The PR #20 orders replace the RS order almost entirely.
- The result that formally passed (Breakout BR) is therefore a **different hypothesis**
  from the original one. It was also one of six tests. The shadow paper books test that BR
  order as it was tested, not the original rating.

## Probably other differences (cannot be checked without the file)
Any of these may differ:
- the components and scaling of "institutional evidence";
- the data windows;
- the universe and periods;
- the decision rule;
- the treatment of missing data.

They will be listed item by item once the original text is available. The text can be
pasted into the chat if the attachment keeps failing.

## How the original can still be tested honestly
- A run of the 75 / 25 rating now would no longer be blind: PR #20's results and the data
  have been seen.
- It can still be pre-registered as **v1.1** with the original definitions:
  - copied verbatim, with no parameter changes;
  - same signals, data, windows, costs and RND benchmark as PR #20.
- It must be reported as **confirmatory of the original plan, but run after unblinding**.
- Like PR #20, it cannot serve as independent confirmation. Only forward data can.

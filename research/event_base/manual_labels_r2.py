"""Convention-normalised labels for the two development sets of extractor v3 (REVIEW_PLAN.md §7).

The original files manual_labels_v1.py (pilot) and manual_labels_val.py (validation) are kept
unchanged. This file re-states labels (five, then two more, see below) under the one rule fixed in §7.1 (the literal §3
definition): the status is decided for the fiscal year in progress on the signal date. When the
only full-year revenue range in the record is for a fiscal year that already ended before the
signal, and the current fiscal year has no range, the status is confirmed_no_suitable_guidance
(subtype prior_fy_range_only), not confirmed_no_raise.

These are non-events under both readings: E and S-covered are unaffected. No other label changes.
"""
from research.event_base.manual_labels_v1 import LABELS as PILOT
from research.event_base.manual_labels_val import LABELS as VAL

G = "confirmed_no_suitable_guidance"
_WHY = "§7.1: only range in the record is for a fiscal year ended before the signal; current FY has no range"

PILOT_OVERRIDES = {
    0: "PYPL FY2017 ended 2017-12-31, signal 2018-01-03",
    1: "BA FY2017 ended 2017-12-31, signal 2018-01-05",
    39: "TSCO FY2021 ended 2021-12-25, signal 2021-12-31",
    68: "TDG FY2024 ended 2024-09-28, signal 2024-10-01",
}
# Added after the first v3 development run, under the §7.1 missing-document rule (a later complete
# Item 2.02 release supersedes a missing one). Both banks/energy issuers give no revenue range in
# the retrieved releases; the originals were "unknown / incomplete_history".
PILOT_OVERRIDES_MISSING_DOC = {
    63: "BAC: the 2024-01-08 Item 2.02 without EX-99 is followed by complete releases 2024-01-12 and 2024-04-16",
    64: "FANG: the last Item 2.02 without EX-99 (2024-04-10) is followed by the complete release 2024-04-30",
}
_WHY_DOC = "§7.1 missing-document rule: a later complete Item 2.02 release supersedes the missing one; no revenue range in the record"

VAL_OVERRIDES = {
    5: "CTAS FY2018 ended 2018-05-31, signal 2018-06-01",
}


def _apply(labels, ov):
    out = []
    for l in labels:
        if l[0] in ov:
            l = (l[0], G, "prior_fy_range_only", l[3], l[4], l[5], l[6], f"{_WHY} ({ov[l[0]]}); originally {l[1]}: {l[7]}", l[8])
        out.append(l)
    return out


def _apply_doc(labels, ov):
    return [(l[0], G, "none_after_superseded_missing_doc", l[3], l[4], l[5], l[6], f"{_WHY_DOC} ({ov[l[0]]}); originally {l[1]}: {l[7]}", l[8])
            if l[0] in ov else l for l in labels]


LABELS_PILOT = _apply_doc(_apply(PILOT, PILOT_OVERRIDES), PILOT_OVERRIDES_MISSING_DOC)
LABELS_VAL = _apply(VAL, VAL_OVERRIDES)

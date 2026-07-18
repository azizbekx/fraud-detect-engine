# Final-dossier judging playbook

## Before release

1. Start the stack with `docker compose up --build` and confirm `/api/health` is green.
2. Keep the practice case frozen. Never edit detector constants for the final case.
3. Confirm deterministic mode works with all LLM environment variables empty.
4. Export the practice audit pack and retain it as the regression baseline.

## When the final dossier arrives

1. Import the folder as a ZIP from the case header.
2. Review coverage before findings. Resolve only visible role/column ambiguities; do not tune names, IDs, dates, thresholds, or amounts.
3. Require 100% parse coverage or record every unsupported/empty source as missing evidence.
4. Review failed reconciliations first, then active findings in ranked order.
5. For every promoted finding, open:
   - the calculation inputs;
   - at least two independent provenance families where the assertion requires corroboration;
   - contradicting evidence;
   - the “why it may be innocent” and “evidence still required” sections.
6. Dismiss weak or explained items. Mark unresolved support gaps as `evidence_requested`, not fraud.
7. Ask the citation-bound chat the same four benchmark questions:
   - Which vendors were created, posted, and paid by the same user?
   - Which same-beneficiary payments aggregate above an extracted approval threshold?
   - Which prior-period receipts or services have only subsequent-period invoices?
   - Which asset additions use repair, replacement, maintenance, or overhaul language?
8. Export the reviewed audit pack. Confirm `verification.unsupported_claims` is zero in `evidence.json` and freeze the ZIP hash.

## Questions for the track auditor

- Does the approval log cover payment approvals, journal approvals, or both?
- What is the allocation of any general year-end accrual to individual obligations?
- Which capitalization policy and materiality threshold govern replacements and major overhauls?

Store answers in the dossier as cited policy evidence. Do not convert them into sample-specific detector constants.

## Five-minute demo order

1. Coverage and immutable hashes.
2. Balanced ledger, subledger ties, dispatch matching, and statement trace.
3. Highest-evidence vendor lifecycle finding and its money flow.
4. Profit-overstatement calculations and the unrelated accrual shown as counter-evidence.
5. Threshold-splitting control breach.
6. One cleared comparator to prove precision.
7. Citation-bound chat, review decision, and self-contained export.

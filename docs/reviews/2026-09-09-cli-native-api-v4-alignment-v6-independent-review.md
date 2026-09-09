# CLI V4 requirement revision 6 independent review

Date: 2026-09-09. Reviewer: cli_v6_req_independent_review.
Lifecycle result: **completed**. Contradictions: **0**. No requirement acceptance is asserted.
Owner route: REVIEW; no additional questions; next stage is second owner disposition.

## Frozen input

- Candidate `docs/requirements/cli-native-api-v4-alignment.v6.md`
  SHA-256 `711a4db7b98b14739f73bd5ce4d9fc6f7f450c7de708f38dc115a113acfaed5e`.
- Input `docs/reviews/2026-09-09-cli-native-api-v4-alignment-v6-first-owner-review.md`
  SHA-256 `f0386bfc74feb2ca4a38bcfbebc483d21d0a6aa5a952db58c7e1f5abdabff29d`.

Reviewer verified both digests at start and finish, all seven normative-source pins and the
r7 comparison pin. Sources were the packet's named primary documents and permitted receipt
definitions. Author self-review and prior reviewer conclusions were not evidence.

## Answers and primary evidence

1. **r8 adoption and authority: consistent.** Candidate lines 21-27 pin each authority separately;
   lines 138-142 disclose frozen Proposed labels, the later owner direction and absent API r8
   independent review. API owner-direction lines 5-19 supplies the exact correction disposition
   and preserves other r7 decisions. The r7/r8 full difference is confined to the receipt model,
   common revision, corresponding verification and authority/history text.
2. **Revision and receipts: consistent.** Candidate lines 126-136 distinguish response revision
   `2026-09-09-r8` from catalog `2026-09-07-v4-r7` and image-to-image from inpaint receipts.
   API r8 lines 165-168, 189-190 and 268-269 agree; H_EDIT/H_INPAINT are retained at 236-237.
   In `src/image_platform/editing.py`, SafetyFilterEvidence (48-51), ImageEditReceipt (92-105),
   ImageToImageAppliedControls (258-264) and ImageToImageReceipt (267-280) match the corresponding
   definitions at fixed V1 commit `4abe752a0913d361aafd906d839e9036514b35c7` byte-for-byte.
   This establishes the retained controls, implementation revision, mask and safety facts, not
   whole-file equivalence or live behavior.
3. **Unchanged scope: confirmed.** Entire sections 2, 3, 4, 6, 7, 8, 9 and 10 are byte-identical
   to accepted v5. Section 5's functional inventory and OAuth distinction are also preserved.
   No output compatibility or additional cutover requirement was introduced.
4. **Boundaries and fallback: consistent.** Candidate 104-107, 135-142, 183-185 and 208-216
   preserve V4-only product traffic, separate public OAuth traffic and separately authorized
   implementation/deployment/release effects. No r7/r8 fallback or weakened receipt validation
   is introduced. API owner-direction 21-25 similarly separates local correction and integration.

## Classified findings

- F01, evidence gap / known unknown, informational: API r8 independent review has not run
  (candidate 138-140; API owner-direction 11-15). Explicitly disclosed; not a contradiction or
  additional acceptance criterion for this bounded CLI requirement review.
- F02, evidence gap / unresolved unknown, informational: API deployment, CLI r8 readiness,
  functional coverage and credential implementation are not established by this source packet
  (candidate 109-119, 140-142, 176-185; v5 owner acceptance 18-22). These remain later work.
- F03, out of scope, informational: actual implementation completion, live responses, deployment,
  default binding and release were neither executed nor verified (candidate 183-185, 208-216).

No optional/future capability is proposed. No new contradiction requires return to a cause phase.

## Primary-agent verification

The primary agent independently read back all seven source pins, compared the unchanged sections,
checked the r8 receipt/revision declarations and owner disposition, and reproduced the four-class
fixed-V1 comparison. Findings above remain classified limitations, not new acceptance requirements.
No candidate bytes, implementation, deployment or external state were changed by this review.

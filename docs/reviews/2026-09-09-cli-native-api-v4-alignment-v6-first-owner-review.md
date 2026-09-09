# CLI V4 requirement revision 6 first owner review

Date: 2026-09-09. Lifecycle step 2. Status: AWAITING_OWNER_ROUTE.

## Exact review subjects

| Subject | Path | SHA-256 |
| --- | --- | --- |
| Candidate | `docs/requirements/cli-native-api-v4-alignment.v6.md` | `711a4db7b98b14739f73bd5ce4d9fc6f7f450c7de708f38dc115a113acfaed5e` |
| Self-review | `docs/reviews/2026-09-09-cli-native-api-v4-alignment-v6-self-review.md` | `01d3db6f12f7d17cd314fc8a5816420e628765bf86b66b5af5221d13c7214921` |

## Proposed independent-review input

One reviewer receives the unchanged candidate, this packet, the seven exact normative sources in
its provenance table, and the prior API design r7 at
`6bd786b13f27d79e6c50cbd4d2b14bf92d2bb2378b43b9f8c9cdfe6427523252` for comparison.
The image repository source root is
`/home/katsumata-m/.codex/worktrees/native-api-v2-interface-alignment/image`.
If needed, the existing image-to-image and inpaint receipt definitions and local correction
validation record may be read as non-normative implementation evidence. Prior reviewer conclusions
are not substitutes for primary evidence.

In scope: explicit adoption of r8's common response revision and dedicated image-to-image receipt;
unchanged inpaint receipt and catalog; preservation of v5's functional and cutover contract.
Out of scope: new capabilities, compatibility requirements, implementation, deployment, live tests,
credentials, publication and actual default binding change.

Acceptance criteria: the r8 reference and receipt semantics match the cited source authority,
all other v5 acceptance criteria remain unchanged, and local implementation/deployment states are
not conflated. API independent review has not run; API deployment and CLI readiness remain later
work. No missing fact is inferred from local test success.

Review questions:

1. Does v6 adopt exactly the owner-selected r8 correction with honest source disposition?
2. Are common response revision, static catalog revision and the two receipt contracts correctly
   distinguished, with controls, implementation revision, mask and safety facts retained?
3. Are sections 2-4 and 6-10 unchanged, with no extra output compatibility or cutover requirement?
4. Does the candidate preserve deployment and implementation boundaries without a hidden fallback?

The reviewer must verify digests and classify findings as contradiction, evidence gap/unknown,
optional/future or out of scope. Return completed or not-reviewable with primary-source evidence.
Do not edit or accept the candidate.

## Owner route

Proposed route: REVIEW, followed by step 4 owner disposition (ACCEPT, REVISE, or eligible REREVIEW).
No added owner questions currently exist. The owner may instead select REVISE,
REVIEW_THEN_REVISE or REVIEW_THEN_DECIDE under the lifecycle. The route remains pending; the owner's
instruction to proceed authorized preparation of this reviewable candidate, not acceptance of
previously unseen bytes. No independent reviewer has been dispatched.

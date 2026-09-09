# CLI to Native API V4 replacement revision 4 self-review

- Date: 2026-09-09
- Lifecycle step: 1 self-review
- Candidate: `docs/requirements/cli-native-api-v4-alignment.v4.md`
- Candidate SHA-256: `7573da268d788eb52788b118bab3f9a12aff32af792cc87a24b5dbbf5b88c7c8`
- Result: `PASS_FOR_FIRST_OWNER_REVIEW`

## Revision boundary

PASS. Revision 4 preserves the parallel `image1`/`image4` implementation, thin packaged `image`
dispatcher, internal `common` package, Native API V4-only product traffic, accepted WorkOS OAuth
transport, shared credential identity and initial Pylint clone detector from revision 3.

It applies the step-4 owner disposition by changing the cutover basis:

- current command parity becomes functional-capability coverage;
- all current leaf commands remain inventory inputs, but multiple commands may map to one capability;
- output, presentation, help-text and exit-status compatibility are excluded;
- readiness is reduced to complete tested capability coverage plus packaged dispatcher proof; and
- no post-cutover `image1` retention window is mandatory.

## Source provenance and prior-authority disposition

PASS. The accepted Native API V4 requirement, accepted V4 design and accepted CLI authentication
contract digests were read back and match the candidate. Revision 3 remains unchanged and unaccepted;
its second owner-review result records `REVISE`. Current implementation commit `1f298f3` supplies the
`image1` functional inventory only and cannot define V4 wire behavior or output compatibility.

`image`, `image1` and `image4` retain the namespace meanings selected in the replacement approach.
No API version or additional public namespace is assigned.

## Scope and exclusions

PASS. In scope are the packaged dispatcher lifecycle, internal code boundary, complete functional
coverage, V4 routing, shared public OAuth behavior, clone detection and proportional cutover
readiness. Implementation, API or edge changes, live requests, credentials, release and Git
publication remain out of scope.

Output compatibility is excluded without excluding functional correctness. The candidate still
requires the requested image/local outcome and accepted V4 envelope, header, byte, metadata and
receipt validation. It does not use byte-for-byte `image1` output as evidence.

## Assumptions and unknowns

The owner-supplied fact that no application currently depends on `image` or `image1` is the basis for
removing output compatibility. If an existing dependent application is later discovered, its actual
contract would require a new requirement decision before cutover.

The functional-coverage matrix is not yet authored. It must enumerate every current leaf command,
derive the distinct capabilities, map every command to them and show no `missing` capability before
cutover readiness can be claimed. This is later design and verification evidence, not a reason to add
command-by-command owner approval to this requirement.

The release-time rollback choice and any live smoke set remain undecided. They are release evidence
and external effects rather than requirement-acceptance criteria.

## Acceptance-criteria check

PASS. Each requirement criterion is decidable:

1. dispatcher binding is provable from a built package;
2. shared-code placement is bounded by validity for both implementations;
3. V4 product routing and prohibited fallbacks are explicit;
4. complete capability coverage is defined without output parity;
5. excluded output dimensions are enumerated;
6. authentication follows the accepted contract;
7. the existing clone detector is identified; and
8. later external effects keep separate authority.

## Proposed independent-review input

The reviewer should receive only this digest-pinned candidate and the resulting first-owner packet.
It should answer:

1. Does the capability definition preserve every operation available through the current leaf
   commands while allowing commands and output presentation to change?
2. Is output compatibility fully removed without weakening image-result correctness or Native API V4
   contract verification?
3. Are the two cutover-readiness conditions sufficient and free of duplicated approval gates?
4. Does `image4` remain V4-only for product API traffic while accepted WorkOS OAuth transport remains
   possible?
5. Are shared code, credentials, clone detection, rollback and later-effect boundaries internally
   consistent with the narrower compatibility premise?

Findings must be classified as contradiction, evidence gap or unresolved unknown, optional or future
candidate, or out of scope. They must not be inserted into the candidate automatically.

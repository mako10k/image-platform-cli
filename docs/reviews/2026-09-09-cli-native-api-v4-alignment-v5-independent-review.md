# CLI to Native API V4 replacement revision 5 independent review

- Date: 2026-09-09
- Lifecycle step: 3
- Status: `COMPLETED`
- Owner route: `REVIEW_THEN_DECIDE`
- Candidate: `docs/requirements/cli-native-api-v4-alignment.v5.md`
- Verified candidate SHA-256: `07fdfc40f90aa17294847b1e1cf469fecc9d322a1dc3ae177d896a82f8d61fe6`
- Candidate changed by reviewer: no
- Owner-added questions: none

## Snapshot verification

All exact owner-reviewed inputs matched their recorded digests:

| Role | SHA-256 |
| --- | --- |
| Requirement candidate | `07fdfc40f90aa17294847b1e1cf469fecc9d322a1dc3ae177d896a82f8d61fe6` |
| Author self-review | `f771573b891f1ffc97b3a8c3365cc4c468ca0a69ce1ef313f2aee78670ed8b79` |
| First owner-review packet | `416b06a2aa5f0675d0231d1fa8d41fe01bac8a8e80f11f8587b0d2163572c5fa` |
| First owner-review result | `2e7dff472f487735832a1ebb36751a6964860bdef5e4aac6dfafd9cc0891e8b0` |

Normative references also matched the candidate-recorded digests: Native API V4 requirement
`e825d34ad807b4236dbd91b84fa09e9fac6086ff7617935dff197988becd5873`, V4 design
`6bd786b13f27d79e6c50cbd4d2b14bf92d2bb2378b43b9f8c9cdfe6427523252`, and CLI authentication
contract `4085db4513d39ba66bd68d215316815401fdb8b8d832e68751ff2bc2de7d4303`.

Mechanical revision 4 to revision 5 comparison shows only requirement revision and predecessor
metadata and correction of credential account identity from issuer plus organization to issuer plus
user subject plus organization ID. No other normative content changed.

## Findings by classification

### Contradiction with reviewed requirement or authoritative source

None. Section 6 now exactly matches the accepted authentication contract's credential identity:
service `image-platform`, account keyed by issuer plus user subject plus organization ID.

### Evidence gap or unresolved unknown — U1

The functional-coverage matrix does not yet exist. Later cutover evidence must demonstrate that every
leaf command and its option-driven semantic variants map to `V4-bound` or `local-common`, with no
`missing` capability. This does not block requirement review because section 8 prevents readiness
until that evidence exists.

### Evidence gap or unresolved unknown — U2

The current implementation still derives the credential account from issuer plus organization only
in `src/image_platform_cli/config.py`. Implementing the accepted three-part key therefore requires a
subject-aware lookup and selection design and tests before `image1` and `image4` can be shown to share
the accepted credential identity. The current implementation is expressly non-normative, so this is
a downstream implementation and verification gap, not a contradiction in revision 5 and not an
output-compatibility requirement.

### Optional or future candidate

None.

### Out of scope

Implementation, credential-store mutation or migration, construction of the functional-coverage
matrix, live requests, binding change, Git publication, deployment and release remain outside this
review and retain separate authority.

## Answers to the four review questions

1. **Credential-identity correction:** yes. Revision 5 requires issuer plus user subject plus
   organization ID, exactly matching the accepted authentication contract and closing revision 4's
   contradiction.
2. **Normative change boundary:** yes. Apart from required revision and predecessor metadata, the
   credential correction is the sole normative revision 4 to revision 5 change.
3. **Shared authentication and output compatibility:** yes at the requirement level. One internal
   shared-authentication component can own the three-part account identity, refresh rotation and
   atomic replacement for both implementations. The correction adds no output-compatibility promise.
   U2 remains for implementation proof.
4. **Prior conclusions:** yes. Functional-capability coverage, exclusion of output compatibility,
   the two readiness conditions, V4-only image-platform product traffic, explicit WorkOS OAuth
   transport, internal `common`, clone detection and separate later-effect authorities remain valid.
   U1 remains until cutover evidence exists.

## Reviewer conclusion

The review is `COMPLETED` with no contradiction. Revision 5 closes the credential-identity
contradiction and otherwise preserves revision 4. U1 and U2 are later implementation and cutover
evidence gaps and do not prevent the exact requirement snapshot from proceeding to lifecycle step 4.

Step 3 does not accept the requirement. Under `REVIEW_THEN_DECIDE`, return this report and the
unchanged candidate to the owner for `REVISE`, digest-preserving `REREVIEW` with a changed or added
question, or `ACCEPT`. Requirement acceptance authorizes none of the later implementation or
external effects.

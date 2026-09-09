# CLI to Native API V4 replacement revision 4 independent review

- Date: 2026-09-09
- Lifecycle step: 3
- Status: `COMPLETED`
- Owner route: `REVIEW_THEN_DECIDE`
- Candidate: `docs/requirements/cli-native-api-v4-alignment.v4.md`
- Verified candidate SHA-256: `7573da268d788eb52788b118bab3f9a12aff32af792cc87a24b5dbbf5b88c7c8`
- Candidate changed by reviewer: no
- Owner-added questions: none

## Snapshot verification

All exact owner-reviewed subjects matched their recorded digests:

| Role | SHA-256 |
| --- | --- |
| Requirement candidate | `7573da268d788eb52788b118bab3f9a12aff32af792cc87a24b5dbbf5b88c7c8` |
| Author self-review | `2603fae82b284066994e339f99bdffeb9510ca5cffe8239d97dfd7ff94c466e1` |
| First owner-review packet | `18bd3ee046c03bcf8d45d929165cf45651ab515bda44261e8e5d58206ed2e374` |
| First owner-review result | `9ed696a079eb6932f029b06752ebbf4d5559734ebfd17fcfae84e9d196fd9ba8` |

Normative references also matched the candidate-recorded digests: Native API V4 requirement
`e825d34ad807b4236dbd91b84fa09e9fac6086ff7617935dff197988becd5873`, V4 design
`6bd786b13f27d79e6c50cbd4d2b14bf92d2bb2378b43b9f8c9cdfe6427523252`, and CLI authentication
contract `4085db4513d39ba66bd68d215316815401fdb8b8d832e68751ff2bc2de7d4303`. Current inventory
commit matched `1f298f39027ac5b6c4028ef45d24b37d481a1c97`.

## Findings by classification

### Contradiction with reviewed requirement or authoritative source — C1 (high)

The candidate says the shared credential account identity is issuer plus organization, while its
declared normative accepted authentication contract requires the account key to contain issuer plus
user subject plus organization ID. Section 6 simultaneously says all entrypoints use the accepted
OAuth-client contract, so omitting the user subject contradicts that authority and the candidate's
own adoption of it.

Earliest causal phase: requirement authoring. Potential effect: two user subjects under one issuer
and organization can resolve to the same credential account and overwrite or consume the wrong
refresh credential. This requires an owner decision and new requirement revision; the reviewer does
not insert a repair.

### Evidence gap or unresolved unknown — U1

The functional-coverage matrix does not yet exist. The requirement's definition can cover semantic
variants expressed below a leaf command, but later evidence must demonstrate that it actually does.
Current examples include filter kind, blend/composite mode, mask-combine operation, color-match
algorithm, flip axis, rotation choice, and inpaint safety-filter behavior. These may be distinct
operations or outcomes even though option spelling and command shape are outside compatibility.

This gap does not block requirement review. The no-`missing` readiness rule prevents a cutover claim
until the matrix supplies the evidence.

### Optional or future candidate

None.

### Out of scope

No material out-of-scope proposal was treated as a finding. Implementation, live smoke, binding
change, release and Git publication remain separately authorized effects.

## Answers to the five review questions

1. **Capability definition:** yes at the requirement-definition level. Distinct operation or local
   outcome, complete coverage of every `image1` capability, mapping every leaf command, and a
   `missing` result preserve functional operations while allowing commands and presentation to
   change. U1 remains until the matrix proves option-driven semantic variants are inventoried.
2. **Output compatibility:** yes. The candidate removes stdout, stderr, JSON, help, stream, command,
   option and exit-status parity while separately retaining requested artifact and file correctness
   and exact Native API V4 envelope, header, byte, metadata and receipt validation.
3. **Readiness conditions:** yes. Condition 1 proves complete tested functional coverage; condition 2
   proves packaged entrypoint and delegate behavior. They test distinct claims and add no per-command
   approval or duplicate blocker gate. Actual cutover and release authority remain separate.
4. **V4-only and OAuth:** yes. The candidate limits V4-only behavior to image-platform product API
   operations and expressly retains WorkOS Device Authorization, refresh and issuer/JWKS transport.
5. **Remaining boundaries:** no as written, because C1 makes credential identity inconsistent with
   the accepted authentication contract. Apart from C1, internal common-code qualification,
   clone-detection escalation, release-time rollback choice and later-effect boundaries are
   internally consistent with the narrower compatibility premise.

## Reviewer conclusion

The output-compatibility exclusion, capability-coverage definition, two readiness checks, V4/OAuth
boundary and proportional controls are internally consistent. One contradiction remains in the
credential account identity, and one later cutover evidence gap remains explicit.

Step 3 does not accept the requirement. Under `REVIEW_THEN_DECIDE`, the unchanged candidate and this
report return to step 4. Because C1 contradicts a declared normative source, `ACCEPT` is not
supportable without returning changed requirement bytes to step 1. `REREVIEW` is available only for
digest-preserving changed or additional review questions.

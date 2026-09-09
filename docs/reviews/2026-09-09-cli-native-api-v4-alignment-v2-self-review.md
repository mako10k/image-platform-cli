# CLI to Native API V4 replacement revision 2 self-review

- Date: 2026-09-09
- Lifecycle step: 1 self-review
- Candidate: `docs/requirements/cli-native-api-v4-alignment.v2.md`
- Candidate SHA-256: `366fee5f10e0662957e7a263dc3218c879d06f844bd4216a9c67e305751587d5`
- Result: `PASS_FOR_FIRST_OWNER_REVIEW`

## Source provenance and prior authority

PASS. Revision 2 preserves the accepted Native API V4 and CLI authentication contracts. It records
revision 1 as an owner-rejected historical snapshot and uses current commit `1f298f3` only as the
behavioral source for `image1`. Existing implementation does not define `image4` semantics.

## Product outcome and scope

PASS. The candidate removes the mixed V1/V4 default state. `image` delegates wholly to `image1`
before cutover and wholly to `image4` afterward. Development may be incremental without exposing a
partial default product. Implementation, cutover and release remain separate effects.

The candidate deliberately broadens the current delivery concept from a two-binding update to a
replacement candidate. After requirement acceptance, the portfolio must be re-derived without
rewriting the completed or suspended work history. Current PERT ordering is not evidence that the
old partial update remains valuable.

## Entrypoint and namespace effects

PASS_FOR_OWNER_DECISION. `image1` and `image4` are new transitional executable names. They are
explicitly identified, limited to migration/rollback roles, and do not replace `image` as the stable
supported name. The owner must accept these external names before implementation.

The dispatcher is fixed by the built package rather than an environment switch. This preserves one
release boundary and avoids different machines silently selecting different API versions.

## Common-code boundary

PASS. `common` is internal and admits only behavior with identical meaning across API versions.
Paths, wire models, error envelopes, headers, receipts and command availability stay versioned. This
prevents a mechanical deduplication goal from becoming an incorrect abstraction rule.

## Authentication, configuration and state

PASS. Credential service/account identity and non-versioned environment names remain stable.
Version-specific adapters cannot access the credential store directly. A changed configuration
meaning requires an explicit migration decision. The split does not create a second authentication
authority.

## Command parity and unknowns

The complete command-to-V4 matrix is not yet authored. The candidate makes every unresolved row a
cutover blocker and forbids silent removal or V1 fallback. This is an evidence gap for cutover, not a
contradiction in the replacement requirement.

An accepted V4 counterpart may not exist for every current CLI operation. Such a row must stay
blocked until the owner separately accepts a command change/removal or another accepted producer
exists. The reviewer must test that this rule is sufficient and has not hidden an impossible
completion contract.

## Duplication control

PASS. `scripts/static-checks.sh` already runs Pylint `duplicate-code` over `src` and `tests` with
`--min-similarity-lines=8`. Revision 2 uses it as detection evidence and retains semantic review of
each clone. It neither adds a redundant tool nor treats a clean report as proof of correct factoring.

## Acceptance and effect boundaries

PASS. The candidate separates requirement acceptance, parity acceptance, implementation checks,
live smoke, default-binding cutover, rollback, publication and release. It does not treat one as
authority for another.

## Proposed independent-review input

The reviewer should receive only the digest-pinned candidate and the first-owner packet. It should
check:

1. whether the dispatcher and three-entrypoint lifecycle actually prevent a partially migrated
   default CLI;
2. whether `image1` preservation and `image4` no-fallback rules are decidable and compatible with
   accepted API authority;
3. whether the parity-matrix blocker rule prevents silent command loss without making completion
   circular or impossible;
4. whether the `common`, credential, configuration and clone-detection boundaries avoid both
   duplication and false abstraction;
5. whether cutover and rollback conditions are sufficient and independently authorized; and
6. whether new executable names or a hidden broader redesign have entered scope without owner
   disposition.

Findings must be classified as contradiction, evidence gap or unresolved unknown, optional or
future candidate, or out of scope. They must not be inserted into the requirement automatically.

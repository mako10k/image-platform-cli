# CLI to Native API V4 replacement requirements, document revision 4

- Status: `DRAFT_FOR_FIRST_OWNER_REVIEW`
- Date: 2026-09-09
- API major version: `4`
- Requirement document revision: `4`
- Lifecycle phase: step 1 complete
- Replaces after acceptance: unaccepted revision 3
- Decision authority: user

## 1. Provenance and authority

This candidate defines a parallel V4 replacement and one final default-entrypoint cutover. It does
not become authoritative until the owner accepts these exact bytes through the requirement-review
lifecycle.

Normative inputs are:

| Role | Path | SHA-256 |
| --- | --- | --- |
| Accepted Native API V4 requirement | image repository `docs/requirements/native-api-v4-interface-alignment.r3.md` | `e825d34ad807b4236dbd91b84fa09e9fac6086ff7617935dff197988becd5873` |
| Accepted Native API V4 design | image repository `docs/design/native-api-v4-interface-alignment.r7.md` | `6bd786b13f27d79e6c50cbd4d2b14bf92d2bb2378b43b9f8c9cdfe6427523252` |
| Accepted CLI authentication contract | `docs/auth-contract.md` | `4085db4513d39ba66bd68d215316815401fdb8b8d832e68751ff2bc2de7d4303` |
| Reviewed predecessor | `docs/requirements/cli-native-api-v4-alignment.v3.md` | `fdbb8f28bc33e39dc4f2a44c12616730b556fa5fffa19582a184bc110569a60b` |
| Revision 3 owner disposition | `docs/reviews/2026-09-09-cli-native-api-v4-alignment-v3-second-owner-review-result.md` | `9efd075061f1d4c0d173f37fecc4de41f6af952d283fca791404c3c209b40ecf` |

The current CLI implementation at commit `1f298f39027ac5b6c4028ef45d24b37d481a1c97` is the
functional inventory source for `image1`, not authority for Native API V4 and not an output-
compatibility baseline. Existing code may be reused only where its meaning is independent of API
version.

The owner reports that no application currently depends on `image` or `image1`. This owner-supplied
product fact removes output compatibility with the current CLI from the requirement and cutover
decision.

## 2. Product outcome

Maintain one stable user command, `image`, while developing a complete V4 implementation beside the
current implementation:

| Entrypoint | Meaning before cutover | Meaning after cutover |
| --- | --- | --- |
| `image` | thin dispatcher to `image1` | thin dispatcher to `image4` |
| `image1` | current CLI implementation | former implementation, while retained |
| `image4` | non-default V4 implementation candidate | implementation behind `image` |

The `image` dispatcher does not parse commands, select API versions per command, inspect mutable
environment flags, or contain product behavior. A packaged release fixes exactly one delegate.
Before cutover every `image` invocation delegates wholly to `image1`; after cutover every `image`
invocation delegates wholly to `image4`.

Development commits may be incremental. Atomicity applies to the user-visible default binding in a
released package, not to Git history.

## 3. Implementation boundaries

The package is divided by responsibility:

```text
image_platform_cli/
  common/       API-version-independent authentication, configuration, credentials, I/O and safety
  v1/           current command composition and current wire adapters
  v4/           replacement command composition and Native API V4 wire adapters
  dispatch.py   one fixed delegate for the packaged default
```

`common` is an internal package, not a separately distributed SDK or public library. Code moves to
`common` only when its behavior and contract are valid for both implementations. Expected common
candidates are:

- OAuth device flow, token validation and refresh;
- OS credential-store access and credential identity;
- non-versioned environment configuration;
- local input validation and safe output-file creation;
- secret-safe diagnostic primitives; and
- presentation helpers deliberately selected for both implementations.

HTTP paths, request and response models, API error envelopes, capability projections, API-version
headers, receipt interpretation, and version-specific command availability remain in `v1` or `v4`.
Similar-looking code is not moved to `common` when its meaning differs.

## 4. Current implementation extraction

The initial extraction makes `image1` the implementation selected by `image`. It must retain the
current CLI's functional operations while that binding is active. Packaging tests prove that
`image` and `image1` invoke the same implementation before cutover.

Exact output compatibility is explicitly excluded. The extraction and V4 cutover do not require
equality of:

- stdout or stderr text, formatting, or stream placement;
- JSON or other presentation shapes;
- help text or examples; or
- exit-status values.

No existing-application compatibility claim is made. Correct creation and validation of requested
image artifacts, credentials, files, and V4 protocol results remains part of the applicable
functional or contract requirement; it is not judged by byte-for-byte comparison with `image1`.

## 5. V4 replacement and functional coverage

`image4` uses only accepted Native API V4 bindings for image-platform product API operations.
WorkOS Device Authorization, token refresh, and issuer/JWKS access continue through the accepted
public OAuth-client transport and are not image-platform product API fallbacks. `image4` must not
call Native API V1, `/v2beta`, provider-compatible endpoints, workers, or Modal directly.

Before cutover, a versioned functional-coverage matrix records every user-facing capability of
`image1`. A capability is a distinct operation or local outcome available to a user; command names,
option spelling and presentation format do not define separate capabilities by themselves. Every
current leaf command is inventoried and mapped to one or more capabilities so that grouping commands
cannot hide a lost operation. Several current commands may map to one capability, and one V4 flow may
replace several current commands. Each capability receives exactly one result:

1. **V4-bound**: `image4` realizes the capability through accepted Native API V4 behavior; or
2. **local-common**: `image4` realizes the capability entirely through accepted local/common behavior;
   or
3. **missing**: `image4` does not yet realize the capability, so cutover is not ready.

The matrix evaluates functional coverage, not command, option, text, JSON, stream, or exit-status
parity. It may define a clearer `image4` command structure when the same capabilities remain
reachable.
The matrix is reviewed as a whole; it does not require separate owner approval for each command.

Every V4 request and completed application response must follow accepted V4 design revision 7,
including exact paths and scopes, common success/error envelopes, request identity, contract
revision, required response headers and operation-specific receipt verification. Output files are
created only after applicable envelope, header, byte, metadata and receipt checks succeed.

## 6. Authentication, configuration and stored state

`image1`, `image4` and the stable `image` command use the accepted public OAuth-client contract.
They never know or forward Modal proxy credentials.

The existing credential service name `image-platform` and issuer-plus-organization account identity
remain shared so the two implementations do not create competing credential stores. Shared
authentication code owns refresh-token rotation and atomic credential replacement; version-specific
API adapters do not access the credential store directly.

Existing non-versioned environment names remain available where needed by the accepted authentication
and endpoint configuration contracts. API-version selection is not a mutable environment option.
The packaged dispatcher and selected implementation determine the API contract.

## 7. Duplication control

The repository's existing mechanical clone detector remains the first check:

```text
pylint --enable=duplicate-code --min-similarity-lines=8
```

It runs over `src` and `tests` through `scripts/static-checks.sh`. A detected clone triggers review
of whether the code expresses a common contract or two version-specific contracts. Passing the
checker does not prove correct abstraction, and code must not be distorted merely to evade a report.

An additional clone-checking dependency is added only if observed duplication escapes the current
check and the alternative supplies useful independent detection.

## 8. Cutover and rollback

`image4` is ready for default cutover when both conditions hold:

1. the functional-coverage matrix contains no `missing` capability and its claims are supported by
   passing local, fake-server, Native API V4 contract, static and built-package tests; and
2. the built package proves that `image`, `image1` and `image4` invoke their intended implementations
   and that changing the packaged delegate switches `image` as one unit.

The actual `image -> image4` binding change and release require separate owner authorization. A live
authenticated smoke request, if selected as release evidence, also requires its own authorization.
Neither requirement acceptance nor local readiness authorizes those external effects.

Cutover does not mutate user configuration to select an API version. This requirement imposes no
mandatory post-cutover retention period for `image1`. A release plan may choose either rebinding to
`image1` or reinstalling the prior package as its rollback mechanism, based on the packaged state
then being released.

## 9. Acceptance criteria for this requirement

This candidate may be accepted only when the owner confirms that:

1. `image` remains a thin packaged dispatcher, initially bound to `image1` and atomically switched
   to `image4` only after readiness;
2. `common` remains internal and contains only behavior valid for both implementations;
3. `image4` product API traffic uses accepted Native API V4 behavior without V1,
   provider-compatible, worker or direct-Modal fallback;
4. cutover readiness means complete functional coverage of `image1` user-facing capabilities,
   supported by tests rather than output or command-by-command compatibility;
5. no stdout, stderr, JSON, help-text or exit-status compatibility with `image1` is required;
6. credentials remain under the accepted shared public OAuth-client contract;
7. the existing Pylint duplicate-code check remains the initial clone detector; and
8. the binding change, live requests and release retain their separate authority boundaries.

## 10. Out of scope

- implementing `image4`, moving code, or changing package entrypoints before acceptance;
- treating `common` as a public SDK;
- promising compatibility to applications that do not currently exist;
- preserving `image1` command, option, output, help or exit-status details as a cutover condition;
- changing Native API V4, OAuth edge, WorkOS, Modal, Cloudflare or DNS;
- live authentication, live requests, credential mutation, deployment or release; and
- commit, push, PR, merge or publication.

## 11. First owner-review decisions

The first owner review decides:

1. whether functional capabilities, rather than individual commands and outputs, are the correct
   coverage unit;
2. whether the two readiness conditions in section 8 are sufficient;
3. whether `image1` retention may remain a release-time choice with no mandatory window;
4. whether `common` should remain an internal package;
5. whether the current Pylint clone check is sufficient as the initial duplication control; and
6. which lifecycle route to take.

No answer is inferred. This candidate authorizes no independent review, coverage-matrix decision,
implementation, external request, credential change, Git publication, deployment or release.

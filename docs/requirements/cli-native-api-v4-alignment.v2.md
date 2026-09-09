# CLI to Native API V4 replacement requirements, document revision 2

- Status: `DRAFT_FOR_FIRST_OWNER_REVIEW`
- Date: 2026-09-09
- API major version: `4`
- Requirement document revision: `2`
- Lifecycle phase: step 1 complete
- Replaces after acceptance: unaccepted revision 1
- Decision authority: user

## 1. Provenance and authority

This candidate replaces the partial in-place update proposed by revision 1. It defines a parallel V4
replacement and one final default-entrypoint cutover. It does not become authoritative until the
owner accepts these exact bytes through the requirement-review lifecycle.

Normative inputs are:

| Role | Path | SHA-256 |
| --- | --- | --- |
| Accepted Native API V4 requirement | image repository `docs/requirements/native-api-v4-interface-alignment.r3.md` | `e825d34ad807b4236dbd91b84fa09e9fac6086ff7617935dff197988becd5873` |
| Accepted Native API V4 design | image repository `docs/design/native-api-v4-interface-alignment.r7.md` | `6bd786b13f27d79e6c50cbd4d2b14bf92d2bb2378b43b9f8c9cdfe6427523252` |
| Accepted CLI authentication contract | `docs/auth-contract.md` | `4085db4513d39ba66bd68d215316815401fdb8b8d832e68751ff2bc2de7d4303` |
| Owner-rejected partial-update candidate | `docs/requirements/cli-native-api-v4-alignment.v1.md` | `674a316d49b7f05423dc230638528a3be50c582366a7828466d9711a50cfe224` |

The current CLI implementation at commit `1f298f39027ac5b6c4028ef45d24b37d481a1c97` is the
behavioral source for `image1`, not authority for Native API V4. Existing code may be reused only
where its meaning is independent of API version.

## 2. Product outcome

Maintain one stable user command, `image`, while developing a complete V4 replacement beside the
current implementation:

| Entrypoint | Meaning before cutover | Meaning after cutover |
| --- | --- | --- |
| `image` | thin dispatcher to `image1` | thin dispatcher to `image4` |
| `image1` | current CLI behavior and current API bindings | temporary rollback/diagnostic entrypoint |
| `image4` | non-default V4 replacement candidate | implementation behind the stable `image` command |

The `image` dispatcher does not parse commands, select API versions per command, inspect mutable
environment flags, or contain product behavior. A packaged release fixes exactly one delegate.
Before cutover every `image` invocation delegates wholly to `image1`; after cutover every
`image` invocation delegates wholly to `image4`.

Development commits may be incremental. Atomicity applies to the user-visible default binding in a
released package, not to Git history.

## 3. Implementation boundaries

The package is divided by responsibility:

```text
image_platform_cli/
  common/       API-version-independent authentication, configuration, credentials, I/O and safety
  v1/           preserved current command composition and current wire adapters
  v4/           replacement command composition and Native API V4 wire adapters
  dispatch.py   one fixed delegate for the packaged default
```

`common` is an internal package, not a separately distributed SDK or public library. Code moves to
`common` only when its behavior and contract are identical for both implementations. Expected
common candidates are:

- OAuth device flow, token validation and refresh;
- OS credential-store access and credential identity;
- non-versioned environment configuration;
- local input validation and safe output-file creation;
- secret-safe diagnostic primitives; and
- presentation helpers whose output contract is intentionally shared.

HTTP paths, request and response models, API error envelopes, capability projections, API-version
headers, receipt interpretation, and version-specific command availability remain in `v1` or
`v4`. Similar-looking code is not moved to `common` when its meaning differs.

## 4. Current implementation preservation

`image1` must preserve the current `image` behavior before any extraction:

- command names, arguments, help and examples;
- stdout, stderr and exit status;
- authentication, scopes and credential identity;
- configured origins and current request paths;
- local validation, offline dry-run and file safety; and
- success and failure behavior covered by the existing tests.

During migration, a characterization test invokes `image` and `image1` with the same deterministic
inputs and proves that the dispatcher returns the selected implementation's stdout, stderr and exit
status without modification. Extraction cannot intentionally change `image1`.

## 5. V4 replacement

`image4` uses only accepted Native API V4 bindings for network operations. It must not call Native
API V1, `/v2beta`, provider-compatible endpoints, workers, or Modal directly.

Before cutover, every current `image1` command is recorded in a versioned parity matrix and receives
exactly one disposition:

1. **V4-bound**: implemented against the accepted V4 binding for the same semantic operation;
2. **local-common**: performs no API operation and is reused without semantic change;
3. **explicitly changed**: changed or removed only by a separately owner-accepted command requirement;
4. **cutover blocker**: no accepted disposition exists, so default cutover cannot occur.

No command may disappear, change meaning, or silently fall back to V1 merely because V4 lacks a
counterpart. The parity matrix is requirement/design evidence and cannot be inferred only from
existing parser branches or route strings.

Every V4 request and completed application response must follow accepted V4 design revision 7,
including exact paths and scopes, common success/error envelopes, request identity, contract
revision, required response headers and operation-specific receipt verification. Output files are
created only after applicable envelope, header, byte, metadata and receipt checks succeed.

## 6. Authentication, configuration and stored state

`image1`, `image4` and the stable `image` command use the accepted public OAuth-client contract.
They never know or forward Modal proxy credentials.

The existing credential service name `image-platform` and issuer-plus-organization account identity
remain stable so cutover does not force a new login solely because the executable changed. Shared
authentication code owns refresh-token rotation and atomic credential replacement; version-specific
API adapters do not access the credential store directly.

Existing non-versioned environment configuration retains its current names. API-version selection is
not a mutable environment option. The packaged dispatcher and selected implementation determine the
API contract. If a configuration field requires different semantics in V4, it must receive an
explicit migration and compatibility decision before cutover.

## 7. Duplication control

The existing repository check is authoritative for mechanical clone detection:

```text
pylint --enable=duplicate-code --min-similarity-lines=8
```

It runs over `src` and `tests` through `scripts/static-checks.sh`. The migration must keep that check
passing. A detected clone triggers review of whether the code expresses a truly common contract or
two version-specific contracts. Passing the checker does not by itself prove correct abstraction,
and code must not be distorted merely to evade a report.

No additional clone-checking dependency is required unless observed duplication escapes the current
check and the new tool demonstrates independent detection value.

## 8. Cutover and rollback

The default `image -> image4` binding may change only when all of these conditions are satisfied:

1. the owner has accepted the complete command parity matrix and every explicitly changed command;
2. `image1` characterization and repository static checks pass;
3. `image4` unit, fake-server, contract and packaging tests pass;
4. a built wheel proves all three entrypoints call their intended implementation;
5. separately authorized authenticated V4 smoke covers the accepted critical command set;
6. no parity-matrix row remains a cutover blocker;
7. rollback identifies an exact prior package revision and preserves credential/config compatibility;
   and
8. the owner separately authorizes the release and default-binding change.

Cutover changes one packaged delegate and does not mutate user configuration to select V4. The first
cutover release retains `image1` as a deprecated rollback/diagnostic entrypoint. Its removal requires
later readback of the stabilization criteria and a separate release decision. `image4` is a
transitional name; the stable supported command remains `image`.

## 9. Acceptance criteria for this requirement

This candidate may be accepted only when the owner confirms that:

1. a parallel replacement with one final default cutover replaces partial in-place migration;
2. `image`, `image1` and `image4` have the lifecycle defined above;
3. `common` remains internal and contains only API-version-independent contracts;
4. `image1` behavior is characterized and preserved during extraction;
5. `image4` has no V1, provider-compatible or direct-Modal network fallback;
6. every current command receives an accepted parity disposition before cutover;
7. credentials and non-versioned configuration survive cutover without an unnecessary login;
8. the existing eight-line Pylint duplicate-code check remains the first clone detector; and
9. cutover, rollback, live requests and release retain their separate authority boundaries.

## 10. Out of scope

- implementing `image4`, moving code, or changing package entrypoints before acceptance;
- treating `common` as a public SDK;
- changing Native API V4, OAuth edge, WorkOS, Modal, Cloudflare or DNS;
- deciding command removals without the parity-matrix lifecycle;
- live authentication, live requests, credential mutation, deployment or release; and
- commit, push, PR, merge or publication.

## 11. First owner-review decisions

The first owner review decides:

1. whether `image1` and `image4` are acceptable transitional executable names;
2. whether a command with no accepted V4 disposition must block cutover as specified;
3. whether one post-cutover release is the minimum `image1` retention window;
4. whether `common` should remain an internal package rather than a separately versioned library;
5. whether the current Pylint clone check is sufficient as the initial duplication control; and
6. which lifecycle route to take.

No answer is inferred. This candidate authorizes no independent review, parity-matrix decision,
implementation, external request, credential change, Git publication, deployment or release.

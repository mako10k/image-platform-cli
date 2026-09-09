# CLI to Native API V4 alignment revision 1 self-review

- Date: 2026-09-09
- Lifecycle step: 1 self-review
- Candidate: `docs/requirements/cli-native-api-v4-alignment.v1.md`
- Candidate SHA-256: `674a316d49b7f05423dc230638528a3be50c582366a7828466d9711a50cfe224`
- Result: `PASS_FOR_FIRST_OWNER_REVIEW`

## Source provenance and prior authority

PASS. The candidate distinguishes API major version 4, contract revision
`2026-09-07-r7`, CLI requirement revision 1, the accepted CLI authentication contract, and the
portfolio task identity. It treats current code and runtime observations as feasibility evidence.
It preserves the accepted Native API V4 and authentication contracts.

## Scope and exclusions

PASS, with an explicit owner decision. The candidate selects capability discovery and the existing
deterministic edit family. This is narrower than aligning every current CLI operation, so acceptance
criterion 1 and first-owner question 1 require the owner to decide whether that is the intended
intermediate meaning of `CLI_V4_ALIGNMENT_READY`. The broader CLI redesign and every unselected
command remain outside this revision.

## Assumptions and unknowns

The candidate relies on these reviewed assumptions:

1. the existing deterministic command family reaches one shared API client operation and can change
   transport/envelope handling without changing command semantics;
2. the V4 capability catalog contains the four named route IDs with exact binding facts; and
3. an explicit zero-dollar cap is valid for the selected deterministic CPU operation.

The following remain unknown pending owner review or later verification:

- whether the owner intends this two-binding increment or all current CLI counterparts;
- whether every existing deterministic command path exercises identical V4 response verification;
- whether the CLI's current output wording needs any user-visible V4 revision indication; and
- live behavior through the public hostname when invoked by the CLI.

The candidate resolves the second and third items conservatively: one shared verifier must cover the
family, and existing user-visible output remains unchanged. Live behavior remains separate evidence.

## Acceptance criteria

PASS. The candidate defines exact selected routes, scopes, request changes, capability mapping,
envelope and request-ID checks, required header/body/receipt equality, safe errors, no-output-before-
verification, OAuth boundaries, compatibility, fake-server coverage, full local checks, and a
separately authorized two-request staging smoke.

## Compatibility and external namespace

PASS. The candidate adopts the already accepted `/v4` namespace and contract revision. It creates
no new API version or command namespace. It forbids fallback after V4 failure and preserves all
unselected CLI routes.

## Normative and non-normative inputs

PASS. Accepted requirement/design and the authentication contract are normative. Current CLI source,
tests, deployed Worker behavior, and the successful GET/POST observations are non-normative and
cannot expand the candidate.

## Proposed independent-review input

The reviewer should receive only the digest-pinned candidate and first-owner packet. It should check:

1. whether the two selected bindings and four capability route IDs exactly match accepted V4 design
   revision 7;
2. whether the selected subset contradicts the portfolio milestone or accepted API requirement's
   separate CLI dispositions;
3. whether request, envelope, header, body, receipt, error, and no-output checks are complete and
   internally consistent;
4. whether zero cost cap, OAuth scope selection, configured origin, and no-fallback behavior preserve
   existing authority boundaries; and
5. whether any broader CLI alignment, redesign, rollout, or implementation preference has been
   introduced as an acceptance blocker.

Findings must be classified as contradiction, evidence gap or unknown, optional or future, or out of
scope. They must not be inserted into the candidate automatically.

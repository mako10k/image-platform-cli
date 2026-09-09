# CLI to Native API V4 alignment revision 1 first owner review

- Date: 2026-09-09
- Lifecycle step: 2
- Status: `AWAITING_OWNER_ROUTE`
- Requirement text changed after self-review: no

## Exact review subjects

| Role | Path | SHA-256 |
| --- | --- | --- |
| Requirement candidate | `docs/requirements/cli-native-api-v4-alignment.v1.md` | `674a316d49b7f05423dc230638528a3be50c582366a7828466d9711a50cfe224` |
| Author self-review | `docs/reviews/2026-09-09-cli-native-api-v4-alignment-v1-self-review.md` | `83ad965bc55cd0654d1ab9da58d06236a83ab87b8522ebfa1549497967f79ca5` |

## Provenance and prior-authority disposition

The candidate adopts Native API V4 requirement revision 3, design revision 7, and the accepted CLI
authentication contract. Current CLI code and successful public-edge observations are
non-normative. The candidate assigns no new external version or namespace and leaves unselected CLI
operations on their current routes.

## In scope

- route `image capabilities` through authenticated `GET /v4/capabilities`;
- project four existing capability items from their exact V4 route IDs;
- route the existing deterministic edit family through `POST /v4/image-operations`;
- adapt only the V4 request and common response envelope;
- verify V4 request identity, version, required headers, bytes, and receipts before file creation;
- preserve current command names, options, output, offline dry-run, OAuth scopes, and secret
  boundaries.

## Out of scope

- every non-selected CLI operation and any new CLI command;
- the broader pre-1.0 command or code-structure redesign;
- API, edge, WorkOS, Modal, Cloudflare, or DNS changes;
- live authentication or requests, deployment, credentials, publication, release, push, PR, or
  merge.

## Acceptance criteria and unknowns

The exact acceptance criteria are in section 6 of the candidate. The material owner decision is
whether two selected bindings are enough for the intermediate milestone. Other unknowns are full
deterministic-family path coverage and later live CLI behavior; the candidate makes the former a
local implementation test obligation and the latter a separately authorized acceptance observation.

## Proposed independent-review questions

1. Do the two bindings and four capability route IDs exactly match accepted V4 design revision 7?
2. Does the selected subset contradict the portfolio milestone or accepted API requirement's
   separate CLI dispositions?
3. Are request, envelope, header, body, receipt, safe-error, and no-output checks complete?
4. Do zero cost cap, OAuth scopes, configured origin, and no-fallback behavior preserve the accepted
   security and compatibility boundaries?
5. Has broader CLI alignment, redesign, rollout, or implementation preference become a requirement
   blocker without owner authority?

## Owner route

Choose exactly one:

- `REVISE`: return directly to candidate authoring;
- `REVIEW_THEN_REVISE`: add owner questions, independently review, then return to authoring;
- `REVIEW_THEN_DECIDE`: add owner questions, independently review, then return for the second owner
  decision; or
- `REVIEW`: independently review the questions above, then return for the second owner decision.

The recommended route is `REVIEW_THEN_DECIDE`. The selected two-binding boundary is a material
interpretation of the intermediate milestone, so independent review should test it before the owner
makes the final acceptance decision.

Independent review cannot edit or accept the requirement. This review authorizes no implementation
or external effect.

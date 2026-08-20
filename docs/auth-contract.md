# Invite-only CLI authentication contract

Status: accepted for local implementation on 2026-08-20; external configuration and live effects
remain separately gated.

## Decision

The staging application uses invite-only registration. A user must accept an organization-bound
WorkOS invitation before authorizing the CLI. The CLI is a first-party Public OAuth Application:
it has a client ID and no client secret.

The primary login protocol is OAuth 2.0 Device Authorization Grant. WorkOS provides this flow for
CLI applications, it does not require a local callback listener, and it works when the CLI host
cannot open a browser. Authorization Code with PKCE over a loopback callback is reserved as a
future fallback and is not part of the first implementation.

## Registration and membership

1. An operator creates an invitation for an exact email address and the intended organization.
2. WorkOS sends the invitation; the CLI does not create or send invitations.
3. The user follows the invitation, completes AuthKit registration and email verification, and
   explicitly joins the organization.
4. Public signup remains disabled. A valid invitation may open signup for its recipient.
5. The CLI accepts tokens only when the access token contains the expected issuer, API audience,
   a user subject, an allowed `org_id`, and the requested image scopes.

Invitations and membership changes are administrative external effects. They require a frozen
email address, organization ID, environment, and maximum write count before execution.

## `image login`

1. Generate a cryptographically random local login transaction identifier used only to correlate
   local state. Do not send it unless the protocol requires it.
2. POST the Public OAuth client ID and least-privilege scopes to the issuer's
   `/oauth2/device_authorization` endpoint.
3. Display the user code and verification URI. Open `verification_uri_complete` in the default
   browser when possible, while retaining a copyable URL for headless use.
4. Poll `/oauth2/token` using the returned interval and Device Code grant. Respect `slow_down`,
   stop on denial or expiry, and impose the server-provided expiry as the hard deadline.
5. Validate the returned access token locally before accepting the login. Require the configured
   issuer, API audience, non-M2M user subject, organization claim, expiry, and requested scopes.
6. Persist the refresh token in an OS credential store. Keep the access token in memory where
   practical; a disk cache, if later justified, must be credential-store protected.
7. Atomically replace a rotated refresh token only after a successful refresh response is fully
   validated.

Initial scopes are `openid profile email offline_access` plus only the image operation scopes the
user requests. Read-only identity commands must not request image mutation scopes.

## Refresh behavior

- Refresh shortly before access-token expiry, not for every command.
- Treat refresh-token rotation as mandatory and replace the stored token atomically.
- On timeout, HTTP 429, or 5xx, retain the current credential and retry with bounded exponential
  backoff while the access token remains valid.
- On terminal `invalid_grant`, remove the unusable local credential and require login again.
- Organization switching is explicit and requires a new Connect authorization/consent flow for
  the selected organization. Refresh does not select an organization; every refreshed token must
  retain the configured `org_id` or be rejected before replacing current state.

## `image logout`

1. Read the session ID from the validated access token when available.
2. Remove local access and refresh credentials first.
3. Offer browser-based WorkOS session logout when a session ID is available. Local logout must
   still succeed if the network or browser step fails.
4. Never call an administrative session-revocation API from the public CLI because that requires a
   server-side API key.

## Storage and output

- Credential key: service `image-platform`, account keyed by issuer plus user subject plus
  organization ID.
- Configuration may contain issuer, audience, client ID, API base URL, selected organization ID,
  and non-secret user display metadata.
- Tokens and codes must never appear in stdout, stderr, shell history, process arguments, debug
  logs, telemetry, or config files.
- `image auth status` reports issuer, user display identity, organization ID, scopes, and expiry;
  it never prints JWTs or refresh tokens.
- Non-interactive environments fail closed when no credential store is available. Plaintext token
  files are not a fallback.

## Staging configuration candidate

- AuthKit issuer: `https://daring-haven-18-staging.authkit.app`
- API audience: `client_01M0F65BD7G48KBFXZ2HT2NQFM`
- Public OAuth client ID: `client_01M0FBDFJ78Q95AF1GB52HR8J5`
- Initial organization: `org_01M0F9R7CCGGMVKAA2G3Z93J0G`
- API base URL: `https://api-staging.image.mk10.org`

These identifiers are non-secret configuration. Production values must be provided separately and
must not silently fall back to staging.

## Acceptance tests before live use

- Device authorization success with a fake issuer.
- Pending, `slow_down`, denial, expiry, malformed response, timeout, 429, and 5xx handling.
- Issuer, audience, subject type, organization, expiry, and scope mismatch rejection.
- Refresh rotation is atomic and preserves the old credential on transient failure.
- Logout removes local credentials even when remote logout fails.
- Secret-redaction tests cover normal, verbose, error, signal, and crash paths.
- One separately approved staging invitation and one bounded live login/API/logout sequence.

## Implementation decision

- Python 3.12 packaged with `uv`; console command `image`.
- Standard-library `argparse` for the command surface, `httpx` for bounded HTTP, `PyJWT` with
  cryptography for JWT/JWKS verification, and `keyring` for OS credential storage.
- Linux, macOS, and Windows are supported only when `keyring` reports a usable non-failing backend.
  Headless systems without such a backend fail closed.

## Deferred decisions

- Whether PKCE loopback fallback is needed after Device Flow usability testing.
- Production invitation ownership, organization policy, support recovery, and audit retention.

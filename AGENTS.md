# Repository Guidelines

## Scope

This repository implements the user-facing CLI for the image platform. Keep it independent from
the API-only `image` repository and the Cloudflare edge gateway. The CLI may call only the public
OAuth and image API surfaces; it must never know or forward Modal proxy credentials.

## Authentication

Follow `docs/auth-contract.md`. The CLI is a public OAuth client and must not contain a client
secret. Treat access tokens, refresh tokens, authorization codes, device codes, and PKCE verifiers
as secrets. Never print them, place them in command arguments, logs, telemetry, crash reports, or
repository files.

External WorkOS mutations, invitations, live authentication, API calls, releases, and remote
publication are separately gated effects. Inspect the exact target first, execute only the
approved bounded effect, and read back the result.

## Development

Do not select a language or dependency stack until the authentication contract is accepted.
Prefer deterministic tests with a fake OAuth issuer and fake API server before any live test.


# Image4 authenticated public smoke

- Executed 2026-09-09 21:53 JST from CLI commit 828adab.
- Target: https://api-staging.image.mk10.org via the real image4 CLI composition,
  existing public OAuth user session, edge gateway and deployed Modal API.
- API deployment: v50, 5d053dd, sha-5d053dd; its deployment record is in the API repository.
- Authorization: owner requested image4 smoke, approved deployment and CLI scope correction,
  then completed login. Command-line LLMThink audit passed without fatal/error/warning findings.

## Results

One GET /v4/capabilities and one POST /v4/image-operations both returned HTTP 200,
API version 4 and contract_revision 2026-09-09-r8. The catalog revision remains
2026-09-07-v4-r7 and returned 25 capabilities. Both CLI invocations exited successfully.

The POST used image4 edit raster crop on a generated 8x4 RGBA PNG, rectangle 2,1,4,2.
The saved 4x2 PNG exactly matched the expected cropped pixels. CLI response verification
checked the envelope, headers, named input, program/command identity and output integrity
before creating the file. Reported estimated and actual API costs were both 0 USD.
Request IDs, CF-Ray values and output SHA-256 are in the adjacent sanitized JSON evidence.

## Authentication correction preceding the smoke

Fresh WorkOS readback found five missing environment permissions and a CLI application still
configured with nine API scopes. The owner approved creation of artifacts:access,
artifacts:delete, artifacts:write, jobs:read and jobs:submit, followed by a scopes-only update
of image-platform-cli-staging. All five permissions and all fourteen CLI scopes were read back;
other application fields were unchanged. One device-authorization check then returned HTTP 200
and validated all required fields; it did not poll for tokens or retain codes. The owner then
logged in normally. The related M2M app remains at its prior nine scopes.

The original failed login response was not retained, so the precise historical error is unknown.
The demonstrated correction is the scope mismatch; the successful user-authenticated smoke is
current evidence. The shared CLI error currently groups HTTP and response-shape failures under
device authorization failed; safe diagnostic refinement remains a separate implementation item.

## Limits

This is a bounded authentication, public transport and deterministic CPU image smoke. It does
not verify generation/inpainting providers, campaigns, artifact persistence or all CLI features.
No paid model inference, retry, default image rebinding, release or Git push was performed.
The image dispatcher still selects image1. Full-suite and built-package cutover validation remain
pending under the owner's focused-test instruction. No credentials or device codes are recorded.

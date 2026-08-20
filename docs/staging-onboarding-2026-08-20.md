# Staging onboarding evidence — 2026-08-20

Environment: WorkOS staging for project `image-platform`.

Organization: `org_01M0F9R7CCGGMVKAA2G3Z93J0G`.

Before the write, exact email-filtered reads found no existing users, organization memberships, or
invitations for either recipient. The owner then authorized the two supplied recipients. Each
invitation was sent once with a seven-day expiry; no retry, resend, or revoke was performed.

| Recipient | Invitation ID | State | Expires at |
| --- | --- | --- | --- |
| `katsumata-m@t-axis.co.jp` | `invitation_01M0FJANMD7CAC62DX3CJ0Z12A` | `pending` | `2026-08-27T12:28:55.820Z` |
| `mako10k@mk10.org` | `invitation_01M0FJAP0WWT3Z4GRNXCADF1WB` | `pending` | `2026-08-27T12:28:56.220Z` |

Independent email-and-organization-filtered list reads returned exactly those pending invitation
records. Invitation tokens and acceptance URLs were not printed or stored.

The owner reported disabling the environment-wide `Sign up` toggle in the Dashboard. WorkOS does
not expose a documented public read API for that toggle, so this remains owner-observed rather than
independently read back.

`katsumata-m@t-axis.co.jp` accepted its invitation, verified its email, and has active organization
membership. Its subject is `user_01M0FJANJM34EKGFPRRDXRG6FP`. The second invitation remains pending;
its user record exists but the email is unverified and it has no organization membership.

The accepted subject was appended to the existing generation allowlist without removing its prior
principal. Local secret metadata reported two unique principals. Modal Secret
`image-platform-composite-policy` was updated in place and hydrated as
`st-l96G2LmFPa3TnHbYFDtgX2`; the deployed App was not redeployed.

Installed CLI Device Flow login then completed for the accepted subject and expected organization.
Credential-store readback reported scopes `email images:generate offline_access openid profile`.
No access or refresh token was printed or stored in the repository. At that checkpoint, live image
generation remained separately gated by its prompt, single-inference ceiling, and cost authorization.

The owner subsequently authorized one 256 by 256 generation with seed zero. The CLI refreshed its
session and sent exactly one generation request; it returned HTTP 422 with request ID
`bc1e9bc8-f217-455a-817b-fa2675a97e93`. No output file was created and no automatic retry occurred.

Diagnosis found that the generation policy compares `Principal.id`, an opaque digest derived from
issuer, subject, and organization, rather than the raw WorkOS `user_*` subject. The dimensions were
within the registered generation profile limits. The raw subject was removed from the allowlist and
replaced with `principal_3812d29dbabcc2fa721fafa72cb938b1`, computed through the API's own
`_opaque_id` implementation. The resulting local allowlist contains two unique principals, and the
corrected Modal Secret update and hydration readback both returned
`st-l96G2LmFPa3TnHbYFDtgX2`. The exhausted generation was not retried; another live request requires
a new explicit authorization.

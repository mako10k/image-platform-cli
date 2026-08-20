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

The environment-wide `Sign up` toggle remains unverified because WorkOS exposes that control in
the Dashboard Authentication settings rather than the documented public API. Live CLI login and
image generation remain unexecuted. After invitation acceptance, the resulting WorkOS `user_*`
subject must be added to the image platform generation allowlist through a separately inspected and
authorized Modal configuration update before live generation can succeed.

# Contributing

Contributions are accepted under the repository's Apache License 2.0. Every
contribution must certify the [Developer Certificate of Origin 1.1](DCO), whose
canonical text is also available at <https://developercertificate.org/>.

Add a sign-off to each commit with:

```console
git commit --signoff
```

The sign-off must use your real name and an email address you are authorized to
use. It records this trailer in the public commit history:

```text
Signed-off-by: Your Name <your.email@example.com>
```

By adding the trailer, you certify the DCO for that contribution. Keep commits
focused, run `./scripts/static-checks.sh` and `uv run pytest`, and never include
credentials, user content, restricted models, or assets without verified
redistribution rights.

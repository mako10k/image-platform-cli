# V4 help navigation and current documentation check

The owner requested a help-coverage check, documentation correction, commit and push.
The former CLI branch was already merged as PR #7; fetched main `75b08f4` had an identical
source tree. The scoped correction starts there on `codex/cli-help-docs`.

## Findings and corrections

- V4 help could traverse parser choices but omitted the guidance, examples, child links and
  parent links promised by README. It now renders those sections offline. Child links and
  option syntax come from the actual parser, and V4-specific guidance covers every topic.
- V1 guidance was not copied wholesale: several of its examples use `--json` flags absent
  from the V4 parser. Every V4 example is now parsed in tests without executing the command.
- README retained a V1 prompt-planning URL, the old login-scope subset, a nonzero random-seed
  claim and V1 receipt/seed printing descriptions. Current V4 routes, fourteen default scopes,
  seed range and actual output behavior are now stated explicitly.
- The earlier 49-command coverage document is a historical baseline. The current parser has
  50 product-command leaves plus help and the I2I alias: 52 leaf paths and 60 total help paths.
  Historical accepted requirements, review snapshots and onboarding evidence remain unchanged.
- I2I guidance explains the Staging typed VAE execution path. Standalone VAE commands,
  optimizer switches and later in-VAE operations are not advertised as available.

## Validation

- 129 focused tests passed: all 60 paths, offline behavior, parent/child navigation, alias,
  invalid topics, exact guidance/tree coverage, all example argument syntax, V4 parser and
  stable dispatcher. Example parsing does not validate user-supplied files, IDs or font digests.
- Required static checks passed: Ruff lint/format, strict Mypy, Xenon and Pylint clone check.
- No new inference, authentication, deployment, release, requirement change or PERT advance.
- Reasoning audit `tmp-cli-help-closeout`: zero fatal/error/warning findings.

The package and local installation readback are recorded below after verification.

# Existing-source rights audit

- Audit date: 2026-08-24
- Audited revision: `25cca2343bb6d6dfa9f7adc2c57a4b50be763181`
- Scope: Git history and tracked repository content receiving Apache-2.0
- Decision owner and legal authority: repository owner

## Result

No repository evidence of an external copyright claimant or incompatible embedded
source was found. The repository owner confirmed authority to approve the legal
decision and license the existing CLI source under Apache License 2.0. This clears
the existing-source rights gate for the audited revision.

The Git audit is evidence about the repository, not independent proof of legal
title. The owner's authority confirmation is a required part of this decision.

## Evidence

- All 39 commits at the audited revision use the same author and committer name.
  They are divided across two historical GitHub identities, with 21 and 18 commits.
  Authenticated GitHub API readback maps both sets to that same author name.
- Commit messages contain no `Co-authored-by`, original-author, copyright, or other
  attribution trailer indicating another contributor.
- The tree has no submodule and no path identified as vendored, third-party,
  generated, copied, patch, or diff content.
- Tracked source, tests, documentation, and configuration have no competing SPDX
  identifier, copyright notice, license boilerplate, or all-rights-reserved notice.
- The owner confirmed legal authority and directed completion of this rights gate on
  2026-08-24.

Future code extraction, contributions, dependencies, and external assets require
their own provenance and license checks; this audit does not pre-clear them.

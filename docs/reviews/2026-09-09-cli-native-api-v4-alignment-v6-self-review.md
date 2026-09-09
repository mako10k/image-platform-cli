# CLI V4 requirement revision 6 author self-review

Date: 2026-09-09. Lifecycle: step 1 complete; first owner route pending.
Candidate: `docs/requirements/cli-native-api-v4-alignment.v6.md`
SHA-256: `711a4db7b98b14739f73bd5ce4d9fc6f7f450c7de708f38dc115a113acfaed5e`

All seven provenance-table source digests were read back. Accepted v5 and its acceptance record
remain unchanged; v6 does not yet supersede them. API r8 is traced to its owner correction direction,
not inferred from passing tests. The Proposed labels in frozen API candidates and absence of an
independent API r8 review are disclosed explicitly.

The difference is confined to revision/provenance metadata, section 5's API contract and receipt
alignment, and section 11's bounded review question. Sections 2-4 and 6-10 are byte-identical to v5.
Functional coverage, output compatibility exclusion, internal common, OAuth credential identity,
clone detection, cutover criteria and separate effects remain unchanged.

API major 4 is unchanged. Response revision becomes 2026-09-09-r8; static catalog remains
2026-09-07-v4-r7. The image-to-image and inpaint receipts remain distinct and complete. No r7/r8
runtime fallback is introduced. Existing CLI implementation is non-normative WIP and was not edited.

Acceptance requires consistency with cited r8 authority and preservation of v5's other requirements.
Remaining unknowns are deployment timing, later CLI readiness and release/cutover decisions. They
are not silently resolved by this candidate. Independent review may verify upstream receipt facts
but must not treat local API tests as deployment evidence or add new capabilities.

Result: ready for first owner review. Proposed review input is the adjacent v6 first-owner packet.

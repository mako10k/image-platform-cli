# Program schema provenance

Public schema exported from DeterministicEditProgram.model_json_schema() at API commit 5d053dd
on 2026-09-09. Local snapshot SHA-256: 97d6b1a8a584f74e315ee778412a053f1170bf50bf37c876a4f45ba825d0c565. No runtime import of private API implementation.
The four schema default factories are RasterSemantics, DeterministicOutputEncoding, identity
AffineMatrix and transparent-black AffineCommand background. Their defaults are explicit in the
normalizer. API semantic validators beyond the JSON schema remain enforced by the public API;
client schema validation does not claim to replace them. Decimal string bounds are checked locally.

Full-suite and built-wheel reruns are deferred per owner's focused-test instruction.

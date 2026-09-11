# CLI / Native API V4 対称性完成要件 v1 First owner review input

- Candidate: `docs/requirements/cli-native-api-v4-symmetry-completion.v1.md`
- Candidate SHA-256: `b4c0b62aa69526638c674eb277415489e94f66dafceaaa6b5e4f983a58107c3d`
- Source audit: `docs/design/cli-v4-api-symmetry-audit.v1.md`
- Source audit SHA-256: `5a348a6170b3759f46f4fd52d982e198b322b66d909fdbdcc3c82271125a85c4`

## Review scope

候補全文を対象とする。既定切替条件は維持し、次のV4 API / CLI対称性マイルストーンを追加する。
現在の未配線はupscaleとrestoreで、`image edit upscale|restore`を提案する。既存i2iのtyped VAE
経路を完成条件に含めるが、公開APIのない独立VAEステージは追加しない。false callable profile
bindingをtruthfulness問題として修正対象に含める。

## Out of scope

V5基盤、独立VAEステージ新設、private/provider/V1面のCLI公開、Web/UI、外部効果。

## Acceptance criteria

候補section 6の7項目。実装状態やテスト成功は要件権限を作らない。

## Unknowns and questions

1. enhancement command taxonomyは提案どおりでよいか。
2. 現在存在しない独立VAE public APIは今回の対称性判定から除外してよいか。
3. owner追加のreview questionがあるか。

## Route after independent review

First owner reviewで選ばれたrouteに従う。`REVIEW_THEN_REVISE`はレビュー後step 1へ戻り、
`REVIEW_THEN_DECIDE`または`REVIEW`はレビュー後step 4へ進む。


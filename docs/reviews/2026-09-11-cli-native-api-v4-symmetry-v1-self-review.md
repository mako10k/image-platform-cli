# CLI / Native API V4 対称性完成要件 v1 セルフレビュー

- Candidate: `docs/requirements/cli-native-api-v4-symmetry-completion.v1.md`
- Candidate SHA-256: `b4c0b62aa69526638c674eb277415489e94f66dafceaaa6b5e4f983a58107c3d`
- Result: step 1 complete; first owner review required

## Provenance

規範入力は、2026-09-11のオーナーによる二つのマイルストーン定義、Accepted CLI切替要件
revision 6、Accepted Native API V4要件revision 3である。現在のコードと対称性監査は
実装状態の非規範証拠としてのみ使用した。

## Scope review

- `image → image4`切替を再定義せず、切替後の対称性マイルストーンを分離した。
- Accepted 25-operation dispositionを維持し、対象外分類を独断で変更していない。
- 未配線と観測したupscale/restoreについて、コマンド名を提案として明示した。
- typed VAEは既存i2i経路の到達条件として扱い、存在しない公開APIから独立CLIを導いていない。
- Discoveryのfalse callable bindingは、Accepted APIのtruthfulness要件に基づく是正対象とした。

## Assumptions and unknowns

- `image edit upscale|restore`の名称は未決定である。
- 独立VAEステージを将来V4に公開するかは未決定である。
- deployed stagingが現在のtyped VAE compositionと同じrevisionかは、この要件候補では確認していない。

## Acceptance and effect boundary

完成条件はAPI/CLI配線、発見可能性、receipt検証、focused contract tests、既存static checksに
限定した。要件受入は実装、PERT更新、commit、push、deploy、live smoke、releaseを許可しない。

## Proposed independent-review input

独立レビューでは、切替条件と対称性完成条件が混同されていないこと、25-operation dispositionを
拡大・縮小していないこと、enhancement名称案のtradeoff、VAE公開境界、discovery truthfulness、
および完成条件の検証可能性を確認する。


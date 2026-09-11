# CLI / Native API V4 対称性監査 v2

- 日付: 2026-09-11
- 性質: オーナー指示に基づく実装範囲と進捗の分類表
- 分母: `src/image_platform_cli/v4/route_contracts.json`に収録された33件の公開method/path契約
- 完了条件: 各契約が既存または新規CLIから直接または複合処理として到達可能で、helpと契約テストから発見・検証できること

## 文書分類

| 文書 | 分類 | 用途 |
| --- | --- | --- |
| `docs/requirements/cli-native-api-v4-alignment.v6.md` | Accepted | `image`から`image4`への切替要件。候補本体のdraft表示は受理したバイト列を保存した履歴であり、受理状態はsecond owner-review resultが記録する |
| `docs/design/cli-v4-functional-coverage.v20.md` | Completed evidence | image1機能網羅、既定切替、ローカル検証の記録 |
| image repo `docs/requirements/native-api-v4-interface-alignment.r3.md` | Accepted, limited use | 25 semantic operationの製品分類。公開CLI配線の件数分母には使わない |
| image repo `docs/design/native-api-v4-interface-alignment.r8.md`とCLIの`route_contracts.json` | Implementation contract | 33件の公開method/path契約とwire contractの分母 |
| `docs/design/cli-v4-api-symmetry-audit.v1.md` | Withdrawn | 25 semantic operationを分母にして未配線を過少報告した監査 |
| `docs/requirements/cli-native-api-v4-symmetry-completion.v1.md` | Withdrawn | 上記の過少集計を前提にした未受理要件候補 |
| 2026-09-11のsymmetry v1 self/first-owner review | Withdrawn | 未受理候補に対するレビュー記録。実装根拠に使わない |

## 33公開契約の配線表

`直接`は一つのCLI操作が当該routeを主目的として呼ぶこと、`複合`はupload、download、
campaign実行などのCLIフロー内で必要なrouteを呼ぶことを表す。CLIのコマンド数とHTTP
route数を一致させる要求ではない。

| # | method/path | CLI到達点 | 形態 | 監査時点 |
| ---: | --- | --- | --- | --- |
| 1 | `POST /v4/artifacts/{artifact_id}/access` | `image artifact download` | 複合 | 接続済み |
| 2 | `POST /v4/artifacts/search` | `image search` | 直接 | 接続済み |
| 3 | `POST /v4/artifacts/{artifact_id}/upload-completion` | `image artifact upload` | 複合 | 接続済み |
| 4 | `POST /v4/artifacts/uploads` | `image artifact upload` | 複合 | 接続済み |
| 5 | `DELETE /v4/artifacts/{artifact_id}` | `image artifact delete` | 直接 | 接続済み |
| 6 | `GET /v4/artifacts/{artifact_id}` | `image artifact show`ほか | 直接・複合 | 接続済み |
| 7 | `GET /v4/artifacts` | `image artifact list` | 直接 | 接続済み |
| 8 | `POST /v4/batch-plans` | `image batch plan` | 直接 | 接続済み |
| 9 | `GET /v4/batch-plans/{plan_id}` | `image batch run`、`iterate` | 複合 | 接続済み |
| 10 | `POST /v4/campaigns/{campaign_id}/cancel` | `image batch cancel` | 直接 | 接続済み |
| 11 | `POST /v4/campaigns` | `image batch run`、`iterate` | 直接 | 接続済み |
| 12 | `GET /v4/campaigns/{campaign_id}` | `image batch status`、`evaluate`、`results` | 直接 | 接続済み |
| 13 | `GET /v4/campaigns` | `image batch list` | 直接 | **未配線** |
| 14 | `GET /v4/capabilities` | `image capabilities` | 直接 | 接続済み |
| 15 | `POST /v4/captions` | `image caption` | 直接 | 接続済み |
| 16 | `POST /v4/enhancements` | `image edit upscale`、`restore` | 直接 | 接続済み |
| 17 | `GET /v4/evaluation-rubrics` | `image batch iterate` | 複合 | 接続済み |
| 18 | `POST /v4/generations` | `image generate` | 直接 | 接続済み |
| 19 | `POST /v4/image-edits` | `image edit image-to-image` | 直接 | 接続済み |
| 20 | `POST /v4/image-operation-batches` | `image edit batch` | 直接 | 接続済み |
| 21 | `POST /v4/image-operation-plans` | `image edit plan` | 直接 | 接続済み |
| 22 | `POST /v4/image-operations` | `image edit run`および各編集コマンド | 直接・複合 | 接続済み |
| 23 | `POST /v4/inpaints` | `image edit inpaint` | 直接 | 接続済み |
| 24 | `POST /v4/jobs/{job_id}/previews/{step_id}/{output}/access` | `image job preview-access` | 直接 | 接続済み |
| 25 | `GET /v4/jobs/{job_id}/previews` | `image job previews` | 直接 | 接続済み |
| 26 | `POST /v4/jobs/{job_id}/cancel` | `image job cancel` | 直接 | 接続済み |
| 27 | `POST /v4/jobs` | `image job submit` | 直接 | **未配線** |
| 28 | `GET /v4/jobs/{job_id}` | `image job show`ほか | 直接・複合 | 接続済み |
| 29 | `GET /v4/jobs` | `image job list` | 直接 | 接続済み |
| 30 | `GET /v4/model-profiles` | `image model-profiles` | 直接 | 接続済み。表示内容の正確性はAPI側で是正対象 |
| 31 | `POST /v4/portrait-mattings` | `image edit matte-portrait` | 直接 | 接続済み |
| 32 | `POST /v4/prompt-plans` | `image prompt optimize` | 直接 | 接続済み |
| 33 | `POST /v4/segmentations` | `image edit segment` | 直接 | 接続済み |

現在の集計は、直接または複合で接続済み31件、未配線2件である。

## VAEとSafetyの境界

VAE encode、latent処理、decodeは、公開V4では`POST /v4/image-edits`の内部物理処理で
あり、独立routeではない。既存の`image edit image-to-image`からこの公開routeへ到達する
経路と、API側でVAE providerへ到達できることを検証する。公開APIにない独立VAEコマンドは
追加しない。

開発時のSafety Checkerは無効のままとし、このCLI配線作業で再導入しない。

## 実装順序

1. enhancementを`image edit upscale`と`image edit restore`へ配線する。
2. operation plan/batchを`image edit plan`と`image edit batch`へ配線する。
3. campaign一覧を`image batch list`、job作成を`image job submit`へ配線する。
4. VAE到達性、model-profile表示、help、文書を整合させる。
5. focused contract testsの後、CLI全体テストと標準static checksを実施する。

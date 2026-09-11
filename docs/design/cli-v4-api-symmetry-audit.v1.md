# CLI / Native API V4 対称性監査 v1

> **撤回済み（2026-09-11）:** この監査は25 semantic operationを分母にしたため、
> 33件ある公開V4 method/path契約の未配線を過少報告した。実装判断には使用せず、
> `cli-v4-api-symmetry-audit.v2.md`を参照する。

- 日付: 2026-09-11
- 性質: 非規範の実装監査
- API要件: image repository `docs/requirements/native-api-v4-interface-alignment.r3.md`
- API要件SHA-256: `e825d34ad807b4236dbd91b84fa09e9fac6086ff7617935dff197988becd5873`
- CLI切替要件: `docs/requirements/cli-native-api-v4-alignment.v6.md`
- CLI切替要件SHA-256: `711a4db7b98b14739f73bd5ce4d9fc6f7f450c7de708f38dc115a113acfaed5e`

## 判定方法

2026-09-11のオーナー指示に従い、`image1`網羅による既定コマンド切替と、その次の
V4 API / CLI対称性マイルストーンを分離する。対称性はHTTPルート数ではなく、Accepted
V4要件の25 semantic operationと、そのCLI dispositionで判定する。

## 監査結果

| V4 semantic operation | V4 API | CLI方針 | 現在のCLI | 判定 |
| --- | --- | --- | --- | --- |
| Capability discovery | `/v4/capabilities` | retain | `image capabilities` | 接続済み |
| Model-profile discovery | `/v4/model-profiles` | add | `image model-profiles` | 接続済み。ただしAPI側に誤ったcallable bindingあり |
| Prompt optimization | `/v4/prompt-plans` | retain | `image prompt optimize` | 接続済み |
| Image generation | `/v4/generations` | retain | `image generate` | 接続済み |
| Image description | `/v4/captions` | retain | `image caption` | 接続済み |
| Image-to-image editing | `/v4/image-edits` | consolidate | `image edit image-to-image` | 接続済み。V4 compositionはtyped VAE providerを使用 |
| Segmentation | `/v4/segmentations` | retain | `image edit segment` | 接続済み |
| Inpaint | `/v4/inpaints` | retain | `image edit inpaint` | 接続済み |
| Generic transform service | V1 only | none | なし | 対象外 |
| Deterministic image operations | `/v4/image-operations`ほか | align | `image edit run`、verify、変換、合成、置換、raster | 接続済み |
| Draw | deterministic operation | align | `image edit raster shape/text` | 接続済み |
| General image composition | future | none | なし | 対象外 |
| Upscale | `/v4/enhancements` | add | なし | **未配線** |
| Restore/enhance | `/v4/enhancements` | add | なし | **未配線** |
| Embedding creation | provider only | none | なし | 対象外 |
| Artifact indexing | internal only | none | なし | 対象外 |
| Text completion | provider only | none | なし | 対象外 |
| Portrait framing plan | V1 only | none | なし | 対象外 |
| Portrait matting | `/v4/portrait-mattings` | retain | `image edit matte-portrait` | 接続済み |
| Product composition | future | none | なし | 対象外 |
| Batch planning | `/v4/batch-plans` | retain | `image batch plan` | 接続済み |
| Campaign management | `/v4/campaigns` | align | run、iterate、evaluate、status、cancel、results | 接続済み |
| Job management | `/v4/jobs` | align | list、show、cancel、previews、preview-access | 接続済み |
| Artifact management | `/v4/artifacts` | align | list、show、download、upload、delete | 接続済み |
| Artifact search | `/v4/artifacts/search` | retain | `image search` | 接続済み |

## VAE境界

公開V4 APIには独立したencode、decode、latent operation、optimizerルートはない。現在の
`image edit image-to-image`は`POST /v4/image-edits`を呼び、APIのModal compositionが
`ModalTypedImageToImageProvider`を選ぶ。このため、既存i2iのVAE内部配線は対称性の対象に
含まれ、独立VAEステージコマンドは現在のAPI対称性からは導かれない。

## 未完了

1. UpscaleとrestoreのCLI名称・引数をオーナー決定する。
2. 決定したCLIを`POST /v4/enhancements`へ接続する。
3. private-only profileを`image.edit`でcallableと表示するAPI discoveryを修正する。
4. 対称性表、CLI help、fake-server contract testを更新する。

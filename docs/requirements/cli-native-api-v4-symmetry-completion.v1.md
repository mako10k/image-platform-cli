# CLI / Native API V4 対称性完成要件 v1

> **撤回済み（2026-09-11）:** この候補は公開ルートの分母を25 semantic operationに
> 狭め、未配線をenhancementだけと誤認したため、要件候補として使用しない。
> オーナー指示と33件の公開契約による実装範囲は
> `docs/design/cli-v4-api-symmetry-audit.v2.md`に記録する。

- Status: `WITHDRAWN`
- Date: 2026-09-11
- Lifecycle: step 1 candidate
- Decision authority: user
- Prior cutover requirement: `docs/requirements/cli-native-api-v4-alignment.v6.md`
- Prior cutover result: `docs/design/cli-v4-functional-coverage.v20.md`

## 1. オーナーが決定済みの境界

1. `image → image4`の切替判断は、`image4`が`image1`の機能を網羅した時点とする。
2. 切替後の次のマイルストーンは、V4 APIで実装した機能とCLIの配線が、V4で可能な
   レベルの対称性まで完了した状態とする。

この要件は切替判断を再実施せず、その次のマイルストーンだけを定義する。

## 2. 対称性の範囲

Accepted Native API V4要件の25 semantic operationを基準にする。CLI dispositionが
`retain`、`add`、`align`または`consolidate`の公開機能は、`image`から同じ意味で利用・
発見できなければならない。対称性は意味上の到達可能性であり、HTTPルートとCLIコマンド
の個数や綴りを一致させる要求ではない。

V1-only、internal-only、provider-compatible-only、futureと既に分類された機能には、
V4 CLIコマンドを追加しない。この分類自体を変更する場合は別のオーナー決定を必要とする。

## 3. 現在の不足と実装候補

非規範監査`docs/design/cli-v4-api-symmetry-audit.v1.md`では、CLI counterpartが必要な
機能のうち、`image.upscale`と`image.restore`だけが未配線である。

この候補では、既存の画像編集taxonomyに合わせて次を提案する。

- `image edit upscale --input FILE --width N --height N --quality-tier deterministic|ai -o FILE`
- `image edit restore --input FILE --quality-tier deterministic|ai -o FILE`

`restore`の出力寸法は入力画像と同じであるため、CLIからwidth/heightは受け取らない。
どちらも`POST /v4/enhancements`だけを呼び、V1、provider-compatible route、worker、Modalを
直接呼ばない。

代替案は次のとおり。

- `image enhance upscale|restore`: API resource名と近いが、新しいtop-level groupが増える。
- `image upscale`と`image restore`: 短いが、既存の`edit`配下taxonomyから外れる。

## 4. VAE関連機能

既存の`image edit image-to-image`は`POST /v4/image-edits`を呼び、そのV4 compositionは
typed VAE providerを使用する。この経路を対称性の完成条件に含める。

現時点のV4 APIには独立したVAE encode、decode、latent operation、optimizer routeがない。
したがって、この要件はそれらの独立CLIコマンドを追加しない。将来それらをV4 APIとして
公開すると決定した場合は、同じ対称性原則によりCLI counterpartも必要になる。

## 5. Discoveryの整合性

`GET /v4/model-profiles`は、実際にそのV4 routeから選択できるprofileだけを
`v4_callable`として表示する。private-only profileを、共通semantic IDだけを理由に
`POST /v4/image-edits`へbindingしてはならない。profile自体を一覧に残す場合は
`platform_only`かつbindingsなしとする。

## 6. 完成条件

1. 25-operation対称性表で、CLI counterpartが必要な全行が接続済みである。
2. オーナーが選んだupscaleとrestoreのCLIから`POST /v4/enhancements`を呼べる。
3. 出力保存前にV4 envelope、headers、receipt、画像bytesの整合性を検証する。
4. i2i CLIからpublic V4 APIを経由してtyped VAE compositionへ到達する。
5. model-profile discoveryがcallableとplatform-onlyを正しく区別する。
6. CLI helpと利用文書から全CLI counterpartを発見できる。
7. API/CLIのfocused contract testsとCLI全体の既存static checksが通る。

## 7. 対象外

- V5の汎用Program、永続latent、汎用DAG、multi-authority実行基盤
- 独立VAEステージAPI/CLIの新設
- V1、provider-compatible API、private workerのCLI公開
- API/CLI以外のWebまたはUI面
- デプロイ、live smoke、release、merge、push

## 8. First owner review

次を決定する。

1. 上記が2026-09-11に示された二つのマイルストーンを正しく分離しているか。
2. enhancementのCLI名称を、提案どおり`image edit upscale|restore`とするか。
3. 独立VAEステージは、公開V4 APIが存在しない現状では今回の対象外でよいか。
4. Lifecycle routeを`REVISE`、`REVIEW_THEN_REVISE`、`REVIEW_THEN_DECIDE`、`REVIEW`から選ぶ。

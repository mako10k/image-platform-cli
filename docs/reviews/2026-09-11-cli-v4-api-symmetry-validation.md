# CLI / Native API V4 対称性実装検証

- 日付: 2026-09-11
- 対象: `docs/design/cli-v4-api-symmetry-audit.v2.md`
- 結果: local implementation validation passed

## 実装結果

埋め込みroute contractに含まれる33件の公開V4 method/pathについて、CLIから直接または
複合フローとして到達できる。今回追加した到達点は次の6コマンドである。

| CLI | V4 route |
| --- | --- |
| `image edit upscale`、`image edit restore` | `POST /v4/enhancements` |
| `image edit plan` | `POST /v4/image-operation-plans` |
| `image edit batch` | `POST /v4/image-operation-batches` |
| `image batch list` | `GET /v4/campaigns` |
| `image job submit` | `POST /v4/jobs` |

複雑なplanner、batch、Job入力は、公開契約の情報をCLI引数へ狭めず、完全なJSON requestを
受け取る。成功応答はroute schemaに加え、該当するgraph、batch、image、Job receiptを
検証してから出力または保存する。

## API側整合性

image repository commit `b8263e6`はmodel profileを広いsemantic IDではなく、実際に
利用できるV4 route IDへ明示的に割り当てる。その後のcommit `dbe352f`で、汎用Job routeが
受理するControlNetとIP-Adapter profileの見落としを修正した。Fluxは`platform_only`、
ControlNetとIP-Adapterは`v4.jobs.create`、typed SD1.5 image-to-image profileは
`v4.image_edits.create`として表示する。

Modal Staging compositionは`ModalTypedImageToImageProvider`をV4 image-edit serviceへ注入する。
VAE Encode、latent denoise、Decodeは`POST /v4/image-edits`内部の物理処理であり、CLIは既存の
`image edit image-to-image`から到達する。独立VAE routeまたはCLIは追加していない。

開発StagingのSafety Checkerは無効のままであり、この変更では再導入していない。

## 検証

- CLI完全テスト: `uv run pytest -q`、635 passed
- CLI標準static checks: `./scripts/static-checks.sh`、Ruff、format、strict mypy、Xenon、Pylint passed
- help navigation: rootとgroupを含む66 path、および全exampleのparseを完全テスト内で検証
- guided Job help: 5件のhelp-only topic、完全なControlNet/IP-Adapter Job JSON、標準`--help`
  とエラーからのrecovery導線をfocused 158 testsとAPI request parserで検証
- API focused tests: Native V4 route/contract、model-profile projection、VAE plan、execution、types、specialized provider passed

CLI packageは作業ブランチからローカル再インストールし、`image`と`image4`でhelp導線を
読み戻した。Modalまたはpublic Stagingへのdeploy、live request、release、merge、pushは
実施していない。

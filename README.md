# TouringProjectV2

バイクでツーリング中のライダーが、インカムのボタンと声だけで AI に質問できる Android アプリ。
AI は現在地と進行方向を踏まえて答え、質問と回答は走ったルートとともに記録に残る。

開発を始めるときは、最初に [PROJECT.md](PROJECT.md)（スライスの定義と進み具合・次にやること・進め方）を読む。

## 構成

このリポジトリはプロジェクト全体の要件・方針・契約・決定を持ち、各ユニットを束ねる。

| パス | 中身 | リポジトリ |
|---|---|---|
| `Android/` | Android アプリ（Kotlin・Jetpack Compose。[adr/0005](adr/0005-native-android-app.md)） | `TouringProjectV2_Android` |
| `Backend/` | API（API Gateway＋Lambda・SAM・東京） | `TouringProjectV2_Backend` |
| `Agent/` | エージェント（Bedrock AgentCore・Strands・us-east-1） | `TouringProjectV2_Agent` |
| `CICD/` | Agent・Backend のデプロイ（非公開） | `TouringProjectV2_CICD` |
| [docs/](docs/README.md) | 要件・方針・契約の現行版。[docs/init/](docs/init/README.md) は初期検討のスナップショット | — |
| [adr/](adr/README.md) | 決定の記録 | — |

## 取得する

```sh
git clone https://github.com/h-akira/TouringProjectV2.git
cd TouringProjectV2
git submodule update --init Android Backend Agent   # CICD は非公開なので除く
```

## 文書の検査と写し

```sh
python3 scripts/check_links.py docs adr README.md   # 相対リンクの切れを検査する
scripts/sync-docs.sh Android Backend Agent CICD # docs/ を各ユニットの docs-parent/ に写す
```

# OTR-4TS3-U1

Open Tuner Receiver。地デジ、BS/110 度 CS、CATV を 4 系統同時に受信できるボードで、ISDB-S3（BS4K）の復調チップへの載せ替えにも対応する。

- ホストとの接続：USB3（FX3）。FPGA（iCE40HX4K-TQ144、中身は HX8K と同じダイ）で 4 系統の TS／TLV を 1 本にまとめる
- 形状：PCIe ロープロファイル（PCIe からは電源だけを取る）と外付け箱の両対応
- 暗号の解除（B-CAS、ACAS）の機能は持たない
- ライセンス（`LICENSES/` を参照）
  - `hw/`：CERN-OHL-S-2.0
  - `fpga/` と `host/`：GPL-2.0-only（px4_drv から派生したコードを含むため）
  - `fx3/`：MIT（FX3 SDK のライブラリはソース非公開のため。ファームのバイナリには Cypress の利用規約がかかる）
  - `docs/`：CERN-OHL-S-2.0（ハードウェア設計資料の一部として）

## ドキュメント

- [docs/research.md](docs/research.md)：事前調査（参照ボードの解析、チップ、先行例、RF・電源・製造の定石、法的な線引き、リスク）
- [docs/decisions.md](docs/decisions.md)：決定事項ログ
- [docs/architecture.md](docs/architecture.md)：ブロック図、電源ツリー、電力見積もり
- [docs/measurement-procedure.md](docs/measurement-procedure.md)：参照ボードの実測手順
- [docs/bom-candidates.md](docs/bom-candidates.md)：部品候補表
- [docs/preverification-plan.md](docs/preverification-plan.md)：ファームウェアとソフトウェアの先行検証計画
- [docs/reference/photos/](docs/reference/photos/)：参照ボード DTV02A-4TS-P の写真

## 状態

設計前の調査段階。回路図はまだない。参照ボードの実測（docs/measurement-procedure.md）を進めている。

## 注意

- 本プロジェクトは、B-CAS や ACAS で暗号化された放送を復号する機能を提供しない。また、提供する予定もない。
- Sony の CXD2856ER と CXD2858ER の情報は、公開されている GPL のドライバと、購入した製品の実測から得たもの。Sony とは関係がなく、NDA に基づく情報は含まない。

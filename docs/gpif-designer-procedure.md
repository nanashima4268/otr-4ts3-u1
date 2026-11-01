# GPIF II Designer の手順（D-41、Windows 機で行う）

目的：FX3 の GPIF II を「16 ビットの同期スレーブ FIFO」に設定するヘッダ `cyfxgpif2config.h` を生成する。
GPIF II Designer は Windows 専用なので、ユーザーが Windows 機で操作する。所要時間は 30 分程度。
画面の項目名は、FX3 TRM 7.15 節（Implementing Synchronous Slave FIFO Interface）に合わせて書いている。実際の画面と違う場合は、近い項目を選び、その旨をメモしておく。

## 1. インストール

1. Infineon の EZ-USB FX3 SDK のページから、**Windows 版**のインストーラーをダウンロードする（Linux 版を入手したときと同じページ）。
2. インストールすると、GPIF II Designer が一緒に入る。

## 2. 雛形からプロジェクトを作る

1. GPIF II Designer を起動する。
2. 同梱の「Cypress Projects」（canned designs）から **Sync Slave FIFO 2 Bit**（同期スレーブ FIFO、アドレス 2 ビット）を開く。
   見つからない場合は、Windows 版 SDK の `firmware\slavefifo_examples\slfifosync\GPIFII_Designer_sync_SlaveFIFO.cydsn` を開く。
3. **File → Save Project As** で、名前を `otr_sfifo16` にして保存する。保存場所は Windows 機の任意のフォルダでよい。

## 3. 設定を確かめて変える

「Interface Settings」タブで、次のとおりになっているか確かめる。違っていれば合わせる。

| 項目 | 値 | 備考 |
|---|---|---|
| Interface type | Slave | |
| Communication type | Synchronous | |
| Clock settings | External | PCLK は FPGA から入れる（50MHz） |
| Active clock edge | Positive | |
| Endianness | Little endian | 1 バイト目が DQ[7:0] に乗る（FPGA の実装と合わせている） |
| **Data bus width** | **16 Bit** | **ここだけ変更する**（雛形は 32 ビットのことが多い。D-39） |
| Address/data bus multiplexed | 外す（非多重） | |
| Number of address pins used | 2 | |
| Flags | FLAGA：thread 0 用の専用フラグ（1 = 満杯でない、0 = 満杯） | FPGA はこのフラグで「次のバッファが空いたこと」を確かめる。FLAGB（部分フラグ）は使わないが、残しておいてよい |

状態遷移（State Machine）は雛形のまま変えない。

## 4. ビルドして送る

1. **Build** を実行する（メニューかツールバーのビルドボタン）。
2. プロジェクトフォルダに `cyfxgpif2config.h` ができる。
3. 次の 2 つを Mac に送る。送り方は共有フォルダでも何でもよい。
   - `cyfxgpif2config.h`
   - プロジェクトフォルダ全体（`otr_sfifo16.cydsn` など）

受け取ったら、私が中身を確かめて `fx3/gpif/` に取り込む。確かめる内容は、16 ビット設定になっていること、Cypress の著作権表示がないこと（D-37）、ファーム側の設定と矛盾しないこと。

## 5. ファーム側で合わせる値（参考）

- **DMA バッファの大きさ**：16KiB（8192 ワード）。FPGA の `gpif_sfifo_wr` のパラメータ `BUFW=8192` と必ず一致させる。
- **PKTEND#**：使わない。バッファは常に満杯にしてから USB に送る。受信を止めるときに残りを押し出す方法は、ファームを書くときに決める。
- **入出力の設定**：`isDQ32Bit = CyFalse` にする。こうすると SPI ブロックが使えるので、FPGA の書き込みに SPI を使える（D-25）。

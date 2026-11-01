# CXD2856ER／CXD2858ER の入手先の調査（2026-11-02）

D-21（ブローカーから少量を買い、検収してから追加する）と R-01（偽物・再刻印品）のための調査。価格と在庫は調査日の表示で、購入はしていない。確かめられなかったものは、その旨を書いた。

## 販売の掲載

| 部品 | 売り手 | 価格 | 最小数 | 状態 | 出典 |
|---|---|---|---|---|---|
| CXD2858ER | Linux4Media（ドイツ） | 10 個以上で €3.36／個、在庫 5,500 | 10 | 記載なし | https://linux4media.de/en/home/79-cxd2858er.html |
| CXD2858ER-T2 | Win Source | US$3.91〜5.87 | 未確認 | 記載なし | https://www.win-source.net/products/detail/sony/cxd2858er-t2.html |
| CXD2858ER | AliExpress（Qixinruite Store） | 2 個で US$15.00、販売実績 0 | 2 | 「新品」と記載、デートコードなし | https://www.aliexpress.us/item/3256811423154686.html |
| CXD2856ER | AliExpress（3 件） | US$6.55〜10.95 | 1〜2 | 「新品」と記載。**商品ページが開けず、売り手・デートコード・単価か組の価格かは未確認** | https://www.aliexpress.us/item/3256809812279271.html ほか |
| CXD2856ER/2858ER/2857ER | Shengyu Electronics（findchips 経由） | 価格なし | — | 在庫 7,000〜13,000 個と表示。ブローカーの見せかけの在庫の可能性が高い | https://www.findchips.com/search/CXD2856ER |
| CXD2856ER-T4、CXD2857ER-T4 | Restar Framos（Sony の代理店系） | captcha で未確認 | — | — | https://www.restarframos.com/product/semiconductors/rf/dvb/cxd2856er-t4-v557/ |
| CXD2856ER | Jotrin、Censtry、utsource ほか | 見積もり依頼 | — | — | https://www.jotrin.com/product/parts/CXD2856ER |

見つからなかったもの：eBay（3 品番とも 0 件）、LCSC、JLCPCB の部品ライブラリ（CXD2856ER は 0 件）、日本の電子部品店。Octopart、OEMsecrets、Win Source の検索は接続を拒否された。

## JLCPCB

- Global Sourcing で取り寄せた部品は JLC の組立にだけ使われ、手元には届かない。組み立てる前にチップ ID を確かめられないので、検収の方針（D-21）と合わない。https://jlcpcb.com/help/article/how-to-use-jlcpcb-global-sourcing-parts-service
- 支給部品（Consign Parts）は使える。手元で確かめた部品を JLC に送る。https://jlcpcb.com/help/article/consignment-part-terms-conditions

## 中古ボードから取り外す方法

px4_drv の README によると、Sony の組（CXD2856ER＋CXD2858ER）を載せているのは PX-MLT5PE・PX-MLT8PE5（5 組）、PX-MLT8PE3（3 組）、DTV02A-4TS-P（4 組）。PX-W3U4・PX-Q3U4 などは東芝と Rafael の IC で、使えない。https://github.com/nns779/px4_drv

ヤフオクの落札（過去 180 日）：PX-MLT5PE は 13 件で平均 ¥31,343（中古 ¥24,000〜39,500）。PX-MLT8PE は 4 件で、ジャンク品が ¥20,300。1 組あたり約 ¥2,500〜6,300 で、ブローカーの 3〜8 倍だが、本物であることがわかっている。https://auctions.yahoo.co.jp/closedsearch/closedsearch/mlt5pe/0

## 検収の方法

- 復調 IC：Linux の cxd2841er ドライバは、レジスタ 0xFD のチップ ID を読み、既知の値と比べる（CXD2837ER は 0xb1 など）。**CXD2856ER の ID の値はどの資料にもなく、px4_drv も ID を確かめていない。** 本物のチップ（参照ボード）で値を読んでおく必要がある。https://raw.githubusercontent.com/torvalds/linux/master/drivers/media/dvb-frontends/cxd2841er.c
- チューナー IC：Linux の helene ドライバも ID を読まない。買った CXD2858ER の確認は、実際に選局できるかどうかでしかできない。
- 刻印と裏の露出パッドを、本物（参照ボード）の写真と比べる。

CXD2856ER や CXD2858ER の偽物の具体的な報告は見つからなかった。ただし、流通量が少なくデータシートも公開されていない部品なので、報告がないことは安全の根拠にならない。

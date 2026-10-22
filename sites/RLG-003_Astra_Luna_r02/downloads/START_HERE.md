# RLG-003 r02 初期設計ベンチマーク

正本は `landing_gear_and_bay.FCStd`。FreeCAD 1.1.4で開く。展開状態の交換形式は `landing_gear.step`、収納状態は `stowed_gear_and_bay.step`。`images/01_deployed.png` と `images/06_stowed_transparent.png` が外観、`drawings.pdf` は主要投影と寸法注記をまとめた10枚のレビュー図面（NTS、製造図ではない）。

`Parameters` の `StateIndex` を0〜10にすると検査対象の姿勢を再現する。0は全伸長、1/2はMLM/MTOM静荷重、3はD1最大圧縮、4は最大ストローク、5/6/7は引込途中、8は収納・扉開、9は収納・扉閉、10は非常伸長完了。再計算には時間がかかる。原本を保つ場合は別名保存してから編集する。

中央オレオ、6輪ボギー、777級を参考にした独自の非直方体脚庫を採用。乾燥質量は約8.01 t。元仕様のMTOM静沈下45%上限にはNG、承認された47%上限では成立する。質量6 tは参考目標。

保存・再読込、全11状態の形状、寸法変更復元、STEP再読込、および収納終了時の脚庫内包含を検証済み。連続した格納経路の最小隙間は判定未完。ダウンロック解除の力伝達、終端吸収、局部強度と購入品の裏付けは未完であり、実機用の完成設計とは扱わない。詳細は `r02_benchmark_findings.md` と `verification.md` を参照。

失敗例は別フォルダ `outputs/failure_examples/`、画像更新履歴は `outputs/design_history/` に保持。ビューワーとサイト掲載は次工程。解析は自実装Pythonで、今回のRLG-003にCalculiXは使用していない。

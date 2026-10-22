# GEAR / LAB — FreeCADベンチマークビューワー

## RLG-003 r02 — 独立した6輪引込主脚サイト

実CAD・図面・解析・失敗例を含む完成サイトを **[sites/RLG-003_Astra_Luna_r02/](sites/RLG-003_Astra_Luna_r02/)** に収録しています。670部品の選択、11姿勢、通常格納のCADサンプル再生、断面・分解、要求追跡に対応しています。

**[公開ビューワーを開く](https://intake.nightly.dedyn.io/sites/RLG-003_Astra_Luna_r02/)** · [ギャラリー](https://intake.nightly.dedyn.io/)（共通パスワードで閲覧）。

```powershell
python -m http.server 8000 --bind 127.0.0.1
# http://127.0.0.1:8000/sites/RLG-003_Astra_Luna_r02/
```

このサブフォルダだけを任意の静的ホストへコピーできます。Three.js・モデル・納入資料を同梱し、CDN、npm install、バックエンドは不要です。ギャラリー配下へ置く場合のパスは `sites/RLG-003_Astra_Luna_r02/`。認証とトップページへの一覧追加は配信側で扱います。

本サイトは設計試行後に作成した閲覧用成果物です。設計のNG・保留・記録間の不一致を明示しており、独立した適合判定・採点は行っていません。既存の汎用ビューワーは引き続き以下の手順で利用できます。

---

FreeCADの設計をThree.jsで表示し、同じ試行の採点・必須ゲート・CSV結果を確認するローカルWebアプリです。Three.js r180を同梱し、外部CDN、アカウント、ビルド、npm installは不要です。

初期データは **FLG-002 / 固定オレオ主脚 / 仕様v2.0** の結果を受け入れる枠です。同じスキーマで書き出した別のFreeCAD設計も読み込めます。

**現時点の同梱データは仕様に基づく未評価の枠だけです。対象のFCStd・STEP・採点結果は未配置のため、実形状・実得点は含めていません。**

## 起動

Windowsではこのフォルダの `start-viewer.cmd` をダブルクリックしてください。Node.js 22以降が必要です（この環境では24で検証）。ブラウザが開かない場合はターミナルに表示されるURLを開きます。

```powershell
node server.mjs
# http://127.0.0.1:8765
```

ポートが使用中なら `node server.mjs --port 8766`。終了はターミナルの `Ctrl+C` です。`index.html` の直接ダブルクリックではES Modulesを読み込めないため、HTTPサーバーから開いてください。サーバーは127.0.0.1にのみ待ち受け、ファイルのアップロード先はありません。

## FreeCADから実設計を表示する

1. FreeCADで対象の `landing_gear.FCStd` を開き、表示したい完成部品を表示します。補助形状や古い形状は非表示にします。
2. `data/export-metadata.template.json` をコピーし、試行ID・仕様版・モデルを実記録に合わせます。試行IDは、例として `FLG-002_r01` を使っています。
3. FreeCADの「表示 → パネル → Pythonコンソール」で次を実行します。`tools_dir` と出力先・メタデータのパスは配置場所に合わせて変更してください。仮想デスクトップでも `tools/` をコピーして同じ関数を使えます。

```python
import sys
tools_dir = r"C:\path\to\freecad-benchmark-viewer\tools"
sys.path.insert(0, tools_dir)
import export_freecad as viewer_export
viewer_export.export_document(
    App.ActiveDocument,
    r"C:\path\to\deliverables\benchmark.json",
    metadata_path=r"C:\path\to\export-metadata.json"
)
```

4. ブラウザの「結果を読み込む」から生成された `benchmark.json` を選ぶか、画面へドロップします。部品名、色、材質（登録がある場合）、体積、ワールド座標のメッシュを表示します。
5. 恒常的な初期表示にする場合は、生成JSONを **このフォルダの `data/benchmark.json` にコピー**して再読込してください。元のFCStdはこの操作で変更しません。

詳細な書出し条件は [tools/README.md](tools/README.md) を参照してください。FCStd / STEPをブラウザで直接解釈する機能はありません。STEPはFreeCADで開いて同じ手順でJSONに変換します。STLは複数ファイルをまとめて直接読めますが、材質・色・単位の情報は保持されず、mmとして扱います。

## ベンチマーク結果を表示する

`data/evaluation.template.json` をコピーし、実際のレビュー結果を記入します。CAD JSONと同時、またはCADの読込後に読み込めます。

- `run.id`: CAD JSONと同じ試行ID。異なる試行の評価は読込を拒否します。
- `evaluation.status`: `unverified`（未検証）、`self-reported`（モデル自己申告）、`verified`（独立検証者が確認した入力値）。アプリ自身が独立検証を行うわけではありません。
- `score`: 未採点は `null`。実際の得点を入力します。`categories` は仕様の7項目、配点合計100点。全項目を採点した場合は、内訳合計と総得点の不一致を拒否します。
- `gates`: G1〜G5の `status` を `pass` / `fail` / `pending` / `unverified`、`detail` に根拠を記入します。
- `source`: 採点者、検証日、報告書・計算・CADの版やハッシュなど、評価根拠を記入します。
- `metrics`: 実測・計算値を `{ "label": "指標名", "value": 数値, "unit": "単位", "source": "根拠" }` の配列で追加します。未解決事項は `issues` に文字列で追加します。

「基準達成（入力値）」は、CADあり、独立検証済みという入力、G1〜G5がすべてPass、追加ゲートもすべてPass、90%以上の得点が揃うと表示します。これは入力結果の集計であり、実機への設計承認を意味しません。

`loads_and_margins.csv`、`requirements.csv`、`bom.csv`、`parameters.csv`、D1/D2時刻歴CSVなどを追加すると「CSV・時刻歴」に列名を維持した表を表示します。数値列が2列以上あればX/Yを選んで折れ線グラフを表示できます。単位は列名に明記してください。CSVはUTF-8を使用します。空欄・単位付き文字列が混じる列は数値グラフの候補にしません。

時刻歴をJSONに含める場合は、トップレベルに次の形式を追加できます。ここに示す値は形式説明用であり、設計結果ではありません。

```json
{
  "timeseries": {
    "name": "ケース名",
    "xLabel": "time",
    "xUnit": "s",
    "series": [{"name": "stroke", "unit": "mm", "values": [[0, 0]]}]
  }
}
```

PDF・Markdown報告書は「ソースファイル」に添付でき、ダウンロードで確認できます。本文を自動解析して合否・採点へ変換する機能はありません。「JSONを書き出す」は現在の形状・評価・JSON時刻歴を保存します。別途追加したCSV・報告書の実体はそのJSONには含まれません。再読込すると手動で読み込んだファイルはクリアされます。

## 3D操作

ドラッグで回転、右ドラッグで移動、ホイールでズーム。部品または一覧をクリックして選択し、チェックで表示を切り替えます。ISO・前・右・上、全体表示（F）、PNG保存、ワイヤー、透過、分解、X/Y/Z断面が使えます。

分解は各部品を表示上で離す操作です。断面は表示をクリップする操作で、切断面の蓋は生成しません。4状態を比較する場合は、FreeCADで状態を切り替えて状態ごとにJSONを書き出し、個別に読み込んでください。動解析の値から勝手にCADのストロークを動かす機能はありません。

## 検証

```powershell
node --test --test-isolation=none tests/schema.test.mjs
python -B -m unittest discover -s tools -p "test_*.py" -v
```

`tests/browser.test.cjs` は開発用のPlaywrightテストです。テスト環境にPlaywrightとChromiumを用意し、サーバー起動後に `node tests/browser.test.cjs` を実行します。`VIEWER_QA_DIR` を指定するとデスクトップ・モバイルのスクリーンショットを保存します。ランタイムにPlaywrightは不要です。

入力上限は合計200MB、メッシュ頂点は合計500万。CSV表は先頭1000行、グラフは先頭5000点を表示します。実モデルが大きい場合は書出し時の `deflection` を増やしてください。原本の寸法を丸める操作ではなく、可視化メッシュの細かさを変える操作です。

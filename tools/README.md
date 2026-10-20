# FreeCAD エクスポータ

`export_freecad.py` は、FreeCAD 文書の表示中の最終形状を
`freecad-benchmark/v1` JSON に変換します。FreeCAD の Python コンソールでは
`exec` で名前空間を汚染せず、次のように読み込みます。

```python
import importlib.util, uuid
path = r"C:\path\to\export_freecad.py"
spec = importlib.util.spec_from_file_location("freecad_export_" + uuid.uuid4().hex, path)
exporter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(exporter)
exporter.export_document(App.ActiveDocument,
                         r"C:\path\to\freecad-export.json",
                         metadata_path=None)
```

GUI マクロからも同じ `export_document(doc, outpath, metadata_path=None)` を
呼べます。`objects` を渡すと、自動選択を使わず、FreeCAD オブジェクトまたは
`Name` / `Label` で指定したソースだけを出力します。

自動選択の方針は次のとおりです。

- `ViewObject.Visibility` と親の可視性が有効で、Shape を持つものだけを対象にする。
- 可視性を取得できない headless 文書では中間形状を推測せず、`objects=[...]` の明示指定を要求する。
- PartDesign Body は Body 自身の最終 Shape だけを対象にし、Body 内の Feature を除外する。
- `App::Part` / Assembly は、表示中の子 Shape があればコンテナを除外して子ごとに分ける。
- `App::Link` はインスタンス変換を推測せず、明示選択・自動選択ともにエラーにする。

Shape は `copy()` し、`obj.getGlobalPlacement()` をそのコピーの
`Shape.Placement` に設定してから `tessellate(0.5)` します。これにより Shape が
保持しているローカル Placement を二重適用せず、入れ子の `App::Part` もワールド
座標へ一度だけ変換できます。座標と bbox は mm、色は `#RRGGBB`、体積は
`volumeMm3` です。STEP の直接インポートは行わず、FreeCAD で開いた文書を通常の
エクスポートに渡してください。

出力の `run.specVersion` は、ベンチマーク仕様がサイドカーで明示されない限り
空文字列です。`freecad-benchmark/v1` は JSON バンドルの transport schema です。
サイドカーは任意の `schema`（指定する場合は同じ値）、`run`、`evaluation`、
`timeseries` を受け付けます。`run.specVersion` はサイドカーで自由に指定でき、
`evaluation.source` は検証資料のパスや説明文字列として保持されます。

`evaluation.status` は明示された `unverified` / `self-reported` / `verified` を
そのまま保持します。エクスポータ自身が形状から採点したり、状態を昇格したりは
しません。ゲートの状態は UI と同じ `pass` / `fail` / `pending` / `unverified`
だけです。数値は有限値でなければならず、スコアは `maxScore` の範囲内でなければ
なりません。評価の値はユーザー提供のメタデータであり、独立検証の証明ではありません。

標準 Python でモックテストを実行できます。

```text
set PYTHONDONTWRITEBYTECODE=1
python -m unittest discover -s . -p "test_*.py" -v
```

FreeCAD の実配置回帰テストは FreeCADCmd 内で unittest のテストスイートを
読み込むと有効になります。通常の Python では FreeCAD 未導入としてスキップされます。
一時ファイルの保存先は環境変数 `VIEWER_TEST_TMP` で指定でき、省略時はシステムの
一時フォルダを使ってテスト終了時に削除します。

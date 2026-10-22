# RLG-003 r02 ビューワー

このフォルダは、CAD・解析結果を相対参照だけで閲覧する独立サイトの入力です。ビルド成果物は `sites/RLG-003_Astra_Luna_r02/` に配置します。公開時の想定URLは <https://intake.nightly.dedyn.io/sites/RLG-003_Astra_Luna_r02/> です。

## ビルド

プロジェクトルートで実行します。

```powershell
python scripts/build_viewer.py --prepare-data
```

これはCAD exporterが `outputs/rlg003-viewer/site/model/` を生成する前でも、画面・証拠・`data/report.json`・ZIPを準備します。3Dデータは、この設計プロジェクトに導入済みのFreeCAD環境で書き出します。GUIと正本は変更しません。

```powershell
& "$env:USERPROFILE\Documents\Codex-LocalData\INTAKECamp2026\freecad-mcp\.venv\Scripts\python.exe" scripts/Run-FreeCADBackend.py cad/rlg003/export_viewer.py --timeout 1800
```

exporter完了後は通常ビルドを実行し、`assembly.json`、`geometry.bin`、CAD SHA-256、メッシュオフセットを検査します。

```powershell
python scripts/build_viewer.py
```

出力は `outputs/rlg003-viewer/site/` と `outputs/rlg003-viewer/RLG-003_Astra_Luna_r02-site.zip` です。ZIPをギャラリーの `sites/` へ展開すると、ZIP内のトップディレクトリがそのまま `sites/RLG-003_Astra_Luna_r02/` になります。

指定納品先は [`naoyamd/freecad-benchmark-viewer`](https://github.com/naoyamd/freecad-benchmark-viewer) の `sites/RLG-003_Astra_Luna_r02/`。このサブフォルダのファイルだけで閲覧でき、元の設計プロジェクトやFreeCADは配信時には不要です。

確認内容と限界は [VERIFICATION.md](VERIFICATION.md) を参照してください。

## ローカル確認

`file:` URLではモジュールとモデルを読み込めないため、プロジェクトルートからHTTPサーバーを起動します。

```powershell
python -m http.server 8000 --bind 127.0.0.1 --directory outputs/rlg003-viewer/site
```

ブラウザで <http://127.0.0.1:8000/> を開きます。サイトは任意のサブパスへ配置できるよう、内部リンクを相対パスで持ちます。

この成果物は認証を実装しません。既存ギャラリーのトップページへの掲載は別途追加してください。ビルドはデプロイやGitHubなど外部サービスへの書き込みを行いません。

格納動作は各qで再計算したCAD姿勢のサンプル再生です。断面はクリップ表示（切断面の蓋なし）、分解は表示上の移動です。製造・実機の組立手順や連続干渉の成立を示すものではありません。Three.jsは既存の `../CADtest/dist/vendor/` から取り込み、MITライセンスを同梱します。

「バンピング・上下動」では0〜600 mmのストローク操作、往復デモ、D1〜D5の記録ストローク時刻歴を0.05〜1倍速で再生できます。S0〜S4の位置を線形補間し、回転を最短経路で補間する表示用近似です。タイヤ接触形状はS0に固定し、内部形状は近いCADサンプルを使用します。タイヤ変形・接地・リンク拘束・荷重応答を連続的に解いたアニメーションではありません。

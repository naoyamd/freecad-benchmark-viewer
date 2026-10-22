# RLG-003 v3.0 検証記録

> 生成器はCADや解析を起動しない。以下は実行時に読み込んだファイルの証拠である。

## CAD再開・状態・パラメータ

- 新規セッション: `True`
- 全11状態の有効part数: `670`（要求確認値666）
- native parametric parts: `601`
- wheel coordinates: `True`
- dimension edit → revert: `True`
- q=0→1→0 sequence rows: `11`
- rigid volume changes: `0` output rows / `0` verification rows

展開: `StateIndex=0` またはS10（q=0、β=-8°、downlock）。収納: S8/S9（q=1、θ=90°、β=0°、S9はDoorAngle=0°）。通常経路はcontrollerの `StateIndex=-1` で q sequence を実行する。再開後にrecomputeし、q=0→1→0と寸法変更→復元を記録する。

## 質量・流体・動解析

- dry mass: **8,010.1 kg** / operating: **8,121.7 kg**（目標6,000 kgは非ゲート）
- unsprung mass: `5,078.5 kg`; bogie inertia: `6,101.488 kg m²`
- motion-boundary rows: `19` (source is recorded in run_record.md)
- D4 bottom margin: `2.082 mm` (analysis summary dynamic cases); 物性・実験相関はレビュー保留
- gas exact check: **Pass**; oil charge conservation: **Fail**
- clearance overall: **inconclusive**; S9 containment: `pass`

最新解析のD1〜D4がno-bottom/no-cavitationでも、D4は接触境界へ近い。D5感度、材料許容、局部構造、実機相関は別保留である。

## 成果物ファイル検査

| ファイル | 存在 | 扱い |
| --- | --- | --- |
| `landing_gear_and_bay.FCStd` | `True` | Pass |
| `landing_gear.step` | `True` | Pass |
| `stowed_gear_and_bay.step` | `True` | Pass |
| `drawings.pdf` | `True` | Pass |
| `images` | `True` | Pass |
| `clearance.csv` | `True` | Pass |
| `kinematics.csv` | `True` | Pass |
| `bom.csv` | `True` | Pass |
| `artifact_json` | `True` | Pass |

## 必須ゲートの判定

| Gate | Status | Evidence / reason |
| --- | --- | --- |
| RLG-14-G1 | **Pending** | analysis structural + materials; 局部強度・締結部・材料保証が未完 |
| RLG-14-G2 | **Pending** | D1-D4 screen=True, convergence=True, D4=2.082 mm; D4の名目余裕とD5感度を明示。タイヤ物性・接触剛性・試験相関は未確認 |
| RLG-14-G3 | **Pending** | analysis/motion/motion_dynamics_summary.json; 動力学再計算済み。終端吸収・解除力伝達・ロック成立の実体根拠が未完 |
| RLG-14-G4 | **Pending** | wheel BOM + brake thermal; 軸受・タイヤ・材料カタログはprovisional |
| RLG-14-G5 | **Pending** | clearance_summary.json; 連続q掃引または許容距離が成立するまでゲートを閉じない |
| RLG-14-G6 | **Pass** | cad_verification.json + exchange/drawings files; 状態検査、寸法復元、交換形式と図面の証拠を照合 |
| RLG-14-G7 | **Pending** | all runtime evidence; Astra主担当・Luna max支援のreference-informed assisted runであり盲検ベンチマークではない |

## 未実施・限界

自実装Python解析のみ。CalculiX/FEM、落下試験、疲労S-N、材料保証、シール・軸受寿命、タイヤメーカー荷重曲線への置換、全機弾性連成は未実施。これは初期設計レビュー資料であり、実機のlife-qualifiedまたはairworthiness-qualified成果物ではない。

# RLG-003 v3.0 初期設計レビュー報告

> 生成元: `scripts/package_rlg003.py` / run ID `RLG-003_Astra_Luna_r02`。入力証拠は生成時に再読込する。
> Astra主担当＋Luna max支援の reference-informed assisted run。単一モデルの盲検ベンチマークではない。
> CAD first。viewerは将来工程、公開・実機搭載承認・耐空性証明は本資料の範囲外。

---

## 1. 範囲と設計ベース

対象は280 t級合成旅客機の左主脚1脚、3軸6輪ボギー、油空圧オレオ、折りたたみ引込機構、脚庫・ふたの初期設計である。寸法はFreeCADの編集可能なパラメータを原典とし、計算は自実装Pythonの予備スクリーニングである。

最新解析summary: `outputs/RLG-003_Astra_Luna_r02/analysis/summary.json`。CAD側は `cad_verification.json` の fresh-session 記録を参照する。dry massは 8,010.1 kg、オレオ内油のみを加えた推定質量は 8,121.7 kg。アクチュエータ・配管・蓄圧器内の全作動油は含めていない。6,000 kg目標は非ゲートとし、現状の 8.01 tを記録する。

材料値、タイヤ代理曲線、ブレーキ炭素、軸受候補は初期仮定または候補である。供給者保証値・熱処理・寸法公差・航空用途の承認を完了したとは扱わない。

---

## 2. CAD構成と状態再現

`Gear / Leg / Slider / Bogie / Bay / Doors / Fixture / Envelopes / FluidVolumes` の役割を分け、主要構造はFreeCAD native primitives/booleansとパラメータ式で構成する。6輪IDはFI、FO、MI、MO、RI、RO。S0は下ろし全伸長、S4は最大圧縮、S5〜S7は引込途中、S8/S9は収納、S10は非常伸長完了として確認する。

現行検査値: `670` parts / 11 states、native parametric `601`、wheel coordinates=True、dimension edit revert=True。剛体volume changesは `0` 件である。

収納経路の連続掃引は `clearance_summary.json` を原典とする。現行証拠のstatusがfailまたはinconclusiveなら、途中姿勢を合格扱いしない。S9の幾何containmentと、脚庫底が開口であることは別々に記録する。

---

## 3. 荷重・オレオ・動解析

r02は外付け荷重支持ばねを撤去し、中央オレオのガスばねで静荷重を支える。ガス初期容積65 L、20°Cで9.20 MPa絶対圧、補助ばね係数0。MTOM静沈下約46.56%は元仕様45%に対してNG、承認された改訂上限47%に対して成立。動的D1〜D5はタイヤ代理曲線、油減衰、ボギーピッチを含む自実装モデルで評価し、計算上の成立と物性・試験による裏付けを区別する。

| ケース | max stroke | tire deflection | tire bottom margin | cavitation | energy residual |
| --- | ---: | ---: | ---: | --- | ---: |
| D1 | 435.5 mm | 158.1 mm | 111.917 mm | なし | 1.056 % |
| D2 | 272.7 mm | 106.2 mm | 163.785 mm | なし | 1.715 % |
| D3 | 456.2 mm | 168.9 mm | 101.079 mm | なし | 0.814 % |
| D4a | 456.5 mm | 267.9 mm | 2.082 mm | なし | 1.162 % |
| D4b | 456.5 mm | 267.9 mm | 2.082 mm | なし | 1.162 % |
| D5 | 489.7 mm | 189.4 mm | 80.598 mm | なし | 1.334 % |

D4の名目底付き境界までの最小値は 2.082 mm（analysis summary dynamic cases）。余裕は小さく、接触剛性・タイヤ物性と実験相関は未確認。ガス exact=Pass、oil charge conservation=Fail。

引込・非常伸長は現行CADの乾燥質量・重心・投影面積、12 L蓄圧器、20°カム開始角を入力して再計算した。analysis/motion/motion_dynamics_summary.jsonに24通常条件と15非常条件の動力学を収録。慣性は中央慣性テンソルのトレースを用いた上界、投影面積はBRep包絡長方形の和集合という保守的近似。全作動油質量、解除伝達機構、ロック時間、終端緩衝は未確定。準静的retraction_summary.jsonのPASSをG3の完成判定に流用しない。

---

## 4. 車輪・ブレーキ・材料

タイヤは成長外径・幅、トレッド溝、側壁、ビード、空洞、ライナー相当を持つ代表形状とし、リム分割、ハブ、対向軸受、シール、肩・スペーサー・ナット・正ロックを荷重経路へ置く。多板ブレーキは各輪へロータ／ステータ／トルクチューブ／ピストンハウジング／配管・速センサーを対応させる。

予備熱計算は8 rotor×18 mm（外径520/内径290 mm）、8 stator×16 mm（外径500/内径270 mm）と、キー溝加工後のCAD実測炭素質量を使う。通常停止・RTO・1個不作動を分けて評価する。摩擦、換気、酸化、摩耗、ピストンシール、軸受の実定格は供給者確認前。材料は300M、7050-T7451、carbon-carbonの初期設計仮定値である。

---

## 5. 製造・整備・FMEA

主要鋼部品は鍛造＋機械加工＋熱処理＋研削、アルミ部品は規格材から加工し、圧力面・シール溝・摺動面の粗さと検査を図面へ戻す。閉じた内部空間を組立不能にせず、軸受・シール・タイヤ・ブレーキは減圧・支持・ロックピンの順序を決めて交換する。

| 故障モード | 検出 | 残る機能/対策 |
| --- | --- | --- |
| 窒素低下・油漏れ | 圧力/ストローク監視、外観 | 整備地上支持、隔離、再充填。継続飛行能力は未承認 |
| 1輪/2輪パンク | タイヤ圧・荷重偏り | 残存輪荷重と金属接地を再計算。通常タイヤ定格を流用しない |
| ブレーキ1個不作動 | 速センサー/制動トルク | 11個配分の停止・熱を確認。左右差を監視 |
| 主油圧喪失・ロックセンサー故障 | 圧力・位置不一致 | 限定非常伸長、機械ロック、操作者警告 |
| ピン抜け・ホース挟み込み | 目視/位置検査 | 二次保持、配管取り回し再検証。寿命資格は未実施 |

30,000着陸・60,000伸縮・300,000走行荷重の寿命目標は、適合S-Nデータ、試験、損傷許容評価がないため実証済みとしない。

---

## 6. 質量記録と任意の軽量化候補

現在のBOMはmass-included 595 partsで、dry mass 8,010.1 kg。6,000 kg目標との差は 2,010.1 kg（operating massは別表示）で、目標超過は設計レビュー項目だが必須ゲート扱いにしない。

| 優先 | part ID / 名称 | 質量 kg | 先に確認する案 |
| ---: | --- | ---: | --- |
| 1 | LG-100 / RLG003_MainActLegNIntegralMount | 1,475.2 | 荷重経路・局部強度を再計算して軽量化案を比較 |
| 2 | RLG003-BOGIE-BEAM / BogieBeamWithAnnularSaddles | 610.7 | 荷重経路・局部強度を再計算して軽量化案を比較 |
| 3 | RLG003-AXLE-REAR / AxleTube_REAR_KeywayCut | 332.0 | 荷重経路・局部強度を再計算して軽量化案を比較 |
| 4 | RLG003-AXLE-FRONT / AxleTube_FRONT_KeywayCut | 332.0 | 荷重経路・局部強度を再計算して軽量化案を比較 |
| 5 | LG-270 / LowerForkWithTorqueClevis | 240.8 | 荷重経路・局部強度を再計算して軽量化案を比較 |
| 6 | LG-200 / PistonTube | 239.4 | 荷重経路・局部強度を再計算して軽量化案を比較 |
| 7 | RLG003-AXLE-CENTER-BARREL / CenterAxleBarrel | 181.0 | 荷重経路・局部強度を再計算して軽量化案を比較 |
| 8 | RLG003-FO-TYRE-CARCASS / TyreCarcass_FO | 143.2 | 供給者断面・熱容量・摩耗限界を確認後、形状最適化 |
| 9 | RLG003-RO-TYRE-CARCASS / TyreCarcass_RO | 143.2 | 供給者断面・熱容量・摩耗限界を確認後、形状最適化 |
| 10 | RLG003-MI-TYRE-CARCASS / TyreCarcass_MI | 143.2 | 供給者断面・熱容量・摩耗限界を確認後、形状最適化 |
| 11 | RLG003-MO-TYRE-CARCASS / TyreCarcass_MO | 143.2 | 供給者断面・熱容量・摩耗限界を確認後、形状最適化 |
| 12 | RLG003-RI-TYRE-CARCASS / TyreCarcass_RI | 143.2 | 供給者断面・熱容量・摩耗限界を確認後、形状最適化 |

軽量化は任意の次工程。中央筒、ボギー梁、車軸、ピストン筒の順に、荷重経路と局部強度を保って断面・材料・加工代を再評価できる。6 tへの一致を完成条件にはしない。外付けばね案r01は失敗例として別保存している。

---

## 7. 検証状況・保留事項・出典

| ゲート | 現状 |
| --- | --- |
| G1 荷重と構造 | **Pending** — 局部強度・締結部・材料保証が未完 |
| G2 緩衝 | **Pending** — D4の名目余裕とD5感度を明示。タイヤ物性・接触剛性・試験相関は未確認 |
| G3 引込と非常伸長 | **Pending** — 動力学再計算済み。終端吸収・解除力伝達・ロック成立の実体根拠が未完 |
| G4 車輪と制動 | **Pending** — 軸受・タイヤ・材料カタログはprovisional |
| G5 収納とふた | **Pending** — 連続q掃引または許容距離が成立するまでゲートを閉じない |
| G6 CAD再現 | **Pass** — 状態検査、寸法復元、交換形式と図面の証拠を照合 |
| G7 証拠の整合 | **Pending** — Astra主担当・Luna max支援のreference-informed assisted runであり盲検ベンチマークではない |

STEP/PDF/PNGが未生成またはmanifest未確認なら `verification.md` でPendingとする。新規FreeCADセッションでは `landing_gear_and_bay.FCStd` を開き、`Parameters.StateIndex=0..10` を再計算し、通常系列はcontroller `StateIndex=-1` で `q=0→1→0` を動かす。展開確認はS0/S10（q=0）、収納確認はS8/S9（q=1）。寸法を1つ編集して再計算し、元へ戻す。

FEM/CalculiX、落下試験相関、疲労S-N、シール寿命、実機スピンアップ、材料・軸受の最終認証は実施していない。これらを理由に「全ゲートPass」へ丸めない。

### 参照

- [https://aircraft.airbus.com/sites/g/files/jlcbta126/files/2024-12/AC_A350_1224.pdf](https://aircraft.airbus.com/sites/g/files/jlcbta126/files/2024-12/AC_A350_1224.pdf)（specs/RLG-003-v3/03_sources_and_decisions.md）
- [https://cdn.skfmediahub.skf.com/api/public/0901d19680416a2b/pdf_preview_medium/0901d19680416a2b_pdf_preview_medium.pdf`](https://cdn.skfmediahub.skf.com/api/public/0901d19680416a2b/pdf_preview_medium/0901d19680416a2b_pdf_preview_medium.pdf`)（cad/rlg003/wheels_notes.md）
- [https://www.boeing.com/content/dam/boeing/boeingdotcom/commercial/airports/acaps/777X_Rev_G.pdf](https://www.boeing.com/content/dam/boeing/boeingdotcom/commercial/airports/acaps/777X_Rev_G.pdf)（specs/RLG-003-v3/03_sources_and_decisions.md）
- [https://www.faa.gov/documentLibrary/media/Advisory_Circular/AC25.723-1.pdf](https://www.faa.gov/documentLibrary/media/Advisory_Circular/AC25.723-1.pdf)（specs/RLG-003-v3/01_design_spec.md）
- [https://www.goodyearaviation.com/resources/pdf/Aviation-Databook-2022.pdf](https://www.goodyearaviation.com/resources/pdf/Aviation-Databook-2022.pdf)（specs/RLG-003-v3/01_design_spec.md）
- [https://www.govinfo.gov/content/pkg/CFR-2025-title14-vol1/pdf/CFR-2025-title14-vol1-sec25-473.pdf](https://www.govinfo.gov/content/pkg/CFR-2025-title14-vol1/pdf/CFR-2025-title14-vol1-sec25-473.pdf)（specs/RLG-003-v3/01_design_spec.md）
- [https://www.govinfo.gov/content/pkg/CFR-2025-title14-vol1/pdf/CFR-2025-title14-vol1-sec25-511.pdf](https://www.govinfo.gov/content/pkg/CFR-2025-title14-vol1/pdf/CFR-2025-title14-vol1-sec25-511.pdf)（specs/RLG-003-v3/01_design_spec.md）
- [https://www.govinfo.gov/content/pkg/CFR-2025-title14-vol1/pdf/CFR-2025-title14-vol1-sec25-723.pdf](https://www.govinfo.gov/content/pkg/CFR-2025-title14-vol1/pdf/CFR-2025-title14-vol1-sec25-723.pdf)（specs/RLG-003-v3/01_design_spec.md）
- [https://www.govinfo.gov/content/pkg/CFR-2025-title14-vol1/pdf/CFR-2025-title14-vol1-sec25-729.pdf](https://www.govinfo.gov/content/pkg/CFR-2025-title14-vol1/pdf/CFR-2025-title14-vol1-sec25-729.pdf)（specs/RLG-003-v3/01_design_spec.md）
- [https://www.govinfo.gov/content/pkg/CFR-2025-title14-vol1/pdf/CFR-2025-title14-vol1-sec25-733.pdf](https://www.govinfo.gov/content/pkg/CFR-2025-title14-vol1/pdf/CFR-2025-title14-vol1-sec25-733.pdf)（specs/RLG-003-v3/01_design_spec.md）
- [https://www.govinfo.gov/content/pkg/CFR-2025-title14-vol1/pdf/CFR-2025-title14-vol1-sec25-735.pdf](https://www.govinfo.gov/content/pkg/CFR-2025-title14-vol1/pdf/CFR-2025-title14-vol1-sec25-735.pdf)（specs/RLG-003-v3/01_design_spec.md）

出典URLは仕様・設計ノートから生成時に収集した一次資料候補であり、数値の適用範囲は各要求節に従う。


# r02 初期設計ベンチマークの判定上の注意

## 設計変更と失敗の扱い

1. **r01 外付けばね案：不採用。** 大型コイル2本と前後横梁による荷重支持は、777級を参考にする構成として不適切と判断。画像、CAD、解析方法、NG結果は `outputs/failure_examples/r01_external_springs_rectangular_bay/` に保存。
2. **元のMTOM静沈下45%上限：NG。** r02中央オレオの名目値は46.56%。ユーザーが認めた改訂上限47%では成立。元条件のNGを消さない。
3. **r02初回の脚庫はみ出し：修正済み。** 正側ダウンロック解除部の端部にX座標を二重適用していた。非直方体脚庫から96,509.7 mm³はみ出した旧モデルを `outputs/failure_examples/r02_initial_shaped_bay/` に保存。修正後は両側端部の外側体積0を確認。

## 完成設計としては残る項目

- **連続経路の残余隙間：判定未完。** 静的収納の包含と、全経路の最小隙間は別の要求。タイムアウトや未収束の掃引をPassにしない。最終CSV/JSONの対象モデルと適用範囲を確認する。
- **ダウンロック解除の力伝達：NG／詳細設計不足。** ピンとオフセットした解除シリンダーは状態パラメータに追従するが、その間の伝達リンク・支持と、負荷下での解除力の一貫した設計が未完。位置が動くことだけでは成立を示せない。
- **非常伸長の終端処理：未完。** 独立蓄圧源と運動計算はあるが、終端運動エネルギーを受ける緩衝機構とロック成立時間の実体根拠が不足。theta=0到達をもってダウンロックPassとしない。
- **配管：初期経路。** 中空管とポートはあるが、屈曲ホース、継手、可動部との距離、必要曲げ半径、実機流体系への接続を全て閉じた設計ではない。
- **材料・購入品・局部強度：初期仮定。** 主断面の計算は、ピン穴、キー溝、保持、ねじ、疲労、製造公差や供給者の航空用途適合を実証しない。これらは別途判定が必要。
- **機体形状：独自の仮定。** 777級の配置を参考にした形状であり、メーカー内部図面から復元した脚庫ではない。原仕様の最大領域内で、絞り部・傾斜天井・面取りした収納空間を定義した。

本成果物は「問題なく製造・搭載できる完成主脚」ではなく、形状・計算・失敗根拠を追跡できる初期設計ベンチマークとして評価する。6 tへの一致はユーザー指示により必達条件にしない。Webビューワーは次工程。

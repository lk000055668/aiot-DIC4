# Energy Detective 實驗紀錄

`evaluate.py` 讀取 UCI 的 [Individual Household Electric Power Consumption 資料](https://archive.ics.uci.edu/dataset/235/individual+household+electric+power+consumption)，依論文的重播規則評估逐時預測與異常篩檢。從 DIC4 根目錄執行，將第一個參數換成官方 ZIP 檔所在位置。Python 及套件版本記在 `results/summary.json`。

```powershell
python 'ICEIB paper/experiments/evaluate.py' '<UCI archive.zip>' 'ICEIB paper/experiments/results'
```

## 預測

- 用資料集的原始時鐘解析時間，按整點建格。每小時 60 個有效且不重複的分鐘才計算完整用電量，單位為 kWh。
- 先以小時格的 70% 與 85% 位置切分，再依目標與特徵的完整性過濾。固定森林參數先用於訓練段與驗證段，最後用前 85% 重擬合。兩個模型的最後訓練標籤截止時間均記在摘要。測試時使用當下之前已觀測到的時段。
- `forecast-test.jsonl` 逐一記錄所有排定測試小時的實際值、有效分鐘數與三法預測，`null` 表示缺少完整目標或所需特徵。僅使用四項數值皆存在的列重算各法 MAE 和 RMSE。各自的可用率以所有排定測試小時為分母。

## 異常篩檢

- `anomaly-observed.jsonl` 保留每個測試小時的原始測量、參考數量、參考窗口首尾、median、MAD、分數與狀態。比較閾值 3.0、3.5 和 4.0 的候選數。候選為相對參考集合的偏離。
- `anomaly-synthetic.jsonl` 記錄從已評分的小時以固定種子抽出的 150 個錨點，在相同的歷史參考下分別將每個目標增加 0.5 與 1.0 kWh。原始觀測和兩種注入情境用各自的候選計數。原始資料沒有設備故障標籤。
- 腳本檢查手算分數、缺值、參考不足、MAD 為零，以及參考時間先於目標。對 150 個錨點改動目標和之後的觀測，再確認歷史參考保持一致。

`summary.json` 記錄 ZIP、原始成員檔與腳本的 SHA-256、資料分界、軟體和模型設定、驗證與測試指標、異常檢查和注入結果。Agent 兩條件的模型設定、正式題集、執行日誌及評分資料由 OpenSpec 待辦追蹤。

## Agent 配對評估

`agent-task-candidates.json` 中的 10 題試測及 50 題正式候選來自同一測試資料期間。五種任務各有一題一般與一題邊界試測，以及六題一般與四題邊界正式候選。`expected` 和 `reference` 僅供本機出題、測試與評分。模型接收題目、重播時間與當次取得的工具紀錄。

- `agent_replay.py` 提供瞬時重播、用電量、等長區間比較、異常篩檢、下一小時預報及能源知識。`agent_study.py` 對兩組使用同一起始提示、工具與八次呼叫上限，B 組可以在驗證失敗後修改一次。每一筆執行保留證據、檢查、耗時、token 和可核實成本。
- `agent_reports.py` 依題目配對彙總結果。必填欄位覆蓋率以實際提供的適用欄位為分子，以答案鍵的適用欄位為分母。失敗及逾時的執行提供零欄位，仍保留分母。`review-packet` 產生移除條件標記的評分材料，條件映射與獨立評分結果由研究端保存。
- 正式執行依賴一個已選定的雲端模型配接模組。模組的 `make_model()` 傳回 `configuration`（`provider`、`snapshot`、`settings`、`price_source`）、`maximum_cost_usd(messages)` 和 `generate(messages)`。後者回傳 `action`、`input_tokens`、`output_tokens` 及 `cost_usd`。呼叫前的保守成本上限須包含該請求的可計費用量，實際價格及模型設定隨執行保存。正式總額包含先前凍結的試測用量，未知成本保留原上限。
- 試測前可用 `agent_study.py --archive <UCI ZIP> prepare <candidates.json>` 從原始資料重建候選。使用 `agent_study.py --archive <UCI ZIP> run pilot <candidates.json> <pilot-dir> --adapter <module> --max-usd <approved-budget>` 後，先檢閱試測並修訂題目或提示，再用 `agent_study.py freeze <candidates.json> <pilot-dir> <frozen.json>` 凍結版本。若正式候選有修訂，另存副本並加上 `--reviewed-candidates <reviewed.json>`。正式 `run formal` 使用凍結檔及獨立輸出目錄。依序使用 `agent_reports.py metrics`、`review-packet` 和 `review-metrics` 彙整正式結果和評分。

本機驗證使用預先定義的回應測試執行流程。雲端試測、正式 A/B 及兩位評分者的資料仍待取得。

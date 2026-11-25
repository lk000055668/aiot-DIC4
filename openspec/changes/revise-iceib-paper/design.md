# 修訂設計與章節盤點

## Context

- 使用者提供的連結確認目標是 [Overleaf DIC4](https://www.overleaf.com/project/6b064ca3ec5187a86110dd8c)。修訂前的檔案樹只有以 pdflatex 編譯的 `main.tex`，是含空 Introduction 的 article 模板。當時的可見歷史版本 0 至 1 僅記錄建立 `main.tex`。查詢 Energy Detective、ICEIB、Energy（含封存）沒有找到現稿專案。
- 以下章節與文獻盤點以使用者已確認的 [本機 IEEE 草稿](../../../ICEIB%20paper/main.txt) 為基準。草稿使用 IEEEtran conference 類別，內文含圖、表、公式與 12 筆內嵌文獻，正文寫明實作、模型訓練與正式評估仍待完成。
- 老師指定順序取自 [AGENTS.md](../../../AGENTS.md)。使用者指定 DIC3 `myplan/A2Z outline example.pdf` 為寫作指南，SHA-256 與 [DIC4 內的副本](../../../DIC3-ProjectRefactor/myplan/A2Z%20outline%20example.pdf) 一致，兩者為同一頁「2020 A-Z SOP」。依 O 項用四類工作與五欄比較表，PI 項用既有架構流程和檢查步驟，PM 項以重播時間界線的論證說明預測的時間隔離。ICEIB 投稿要求依官網。

## 目前進度

- 已採用 DIC3 的 A-to-Z 指南，完成章節對照及比較表、流程和時間隔離論證的核對。工作稿採 IEEEtran Conference 格式，若 ICEIB IEEE 軌道另有專用範本，待正式指引公布後核對。
- 預測與異常篩檢結果已回填至 Abstract、Experiments 和 Conclusion，並保留逐時紀錄供重算。Agent A/B 評估及相關重現紀錄待補，正式作者資料依使用者指示暫緩。各項驗收進度見 [待辦清單](tasks.md)。

## Goals / Non-Goals

目標是沿用已確認的現稿，保留可用的研究內容、技術細節和交叉引用，並將每節的修訂連到可核對的證據。此計畫的產出為英文 ICEIB 稿件及其投稿前驗收紀錄。Agent 實作和執行實驗的成果是補寫 Experiments 所需的前置輸入。

## Decisions

### 章節對照

| 老師指定章節 | 本機已寫內容 | A-to-Z 範例對照與修訂 |
| --- | --- | --- |
| Abstract | 有英文摘要及關鍵字，交代家庭用電、單位與歸因問題、Agent 設計、預測及 A/B 評估方案。 | A–E 已有動機、挑戰、方案、方法和評估設定。F（Findings）已填入預測及異常篩檢結果，Agent 評估維持待補。 |
| Introduction | 有動機、可靠性問題、五類任務、研究問題及資料契約、證據追蹤和評估協定等三項貢獻。 | G、H、K 已有基礎。I、J 補現有方法的分類與評析，讓 gap 連到配對設計。L 補依修訂後順序撰寫的文章導讀。 |
| Related Work | 有住宅用電回饋與預測、工具型 LLM 和證據支持，以及建築和家庭能源代理人的相關研究。已有初步研究差異。 | M、N 補各路線的可比較性和本研究切入點。O 採 DIC3 指南，已完成四類研究及五欄的比較，並核對各列引用。 |
| Proposed Design | Data and Analytical Methods 有 replay cutoff、欄位完整度、kW/kWh 換算、MAD 篩檢、三種預測；Agent Architecture 有八元件圖、證據與一次修正；Worked Examples 有三個手算案例。 | PA–PH 以研究目標、資料流程、八元件圖和公式對應。PI 採既有流程圖及檢查步驟。PJ 保留手算示例，PK、PL 交代設計要點及實驗。PM 補半開區間與訓練標籤截止的時間隔離論證。 |
| Experiments | Evaluation Protocol 有分時段切分、共同樣本、三種預測、異常檢查、A/B 題集與評分方式，附預計題型表。Limitations 已列單戶舊資料、設備分組、缺標籤與外部效度。 | Q–T 已補預測與異常篩檢的實際樣本、設定與比較方法。U–V 已回填兩項結果及解讀。Agent 實測仍待補。相關限制納入本節並在結論呼應。 |
| Conclusion | 有設計回顧、欲解決的錯誤和預定評估。 | W、X 回顧研究與方法。Y 報告誤差、可用率及異常篩檢主要結果。Z 交代單戶外推限制、後續場域驗證及待做的 Agent 對照。 |
| References | 有 12 筆內嵌文獻，包括資料集、基準方法、異常判定、能源及 Agent 研究。 | A–Z 範例正文對照至 Conclusion，References 依老師指定章節及 IEEE 規範驗收。核對來源、引用順序、論述對應和預印本的出版狀態。 |

### 實驗證據與作者資料

| 項目 | 驗收所需的證據 |
| --- | --- |
| 資料與預測 | 資料 checksum、時間切分邊界、缺值與完整時段計數、訓練資料與截止時間、最終參數與選擇依據，以及 random forest、persistence、daily seasonal naive 在同一測試交集的 MAE、RMSE、樣本數和各法可用率。保留各時段預測及排除原因。 |
| Agent 對照 | 10 題獨立試測的觀察、凍結的 50 題與答案鍵、A/B 同配置紀錄、每題每條件 3 次（預計 300 次）的實際日誌。彙整整體及分題型任務完成、證據一致性、必填欄位覆蓋、適當限制、不必要拒答、兩位評分者的建議評分與一致程度，以及延遲、工具與修正次數、模型呼叫、token、可核實成本。保留失敗和逾時紀錄。 |
| 異常篩檢 | 算例、時序隔離、閾值敏感度的執行紀錄。若有注入實驗，保留注入清單及分母。若有原始時序案例，保留觀測窗口、歷史參考集、分數與解讀。資料缺設備故障標籤與節電場域測量，成效敘述須符合可驗證範圍。 |
| 重現資訊 | 解析與切分規則、模型版本與設定、提示詞、題集與答案鍵版本、checker 規則、工具／證據／驗證紀錄，以及數字到正文圖表的對應。 |
| 作者欄 | 本機稿註解列提案名單：蔡鈞凱、吳育倫、邱敬倫、蔡昇剛。待確認最終作者名單與順序、各人的正式英文姓名、系所、機構、城市／國家、通訊作者及其電子郵件，以及投稿若要求的其他作者電子郵件。 |

### 套用與核對順序

1. 使用者確認規劃、目標 Overleaf 專案與稿件基準後，以 MCP 取得最新主檔與文獻，核對與上述暫定盤點的差異，再依核准的對照搬移內容。
2. 依老師確認的指南及 ICEIB 範本核對篇幅和圖表配置，並保持原有圖表、公式、文獻及交叉引用可追溯。
3. 從實驗紀錄製作結果圖表，回填 Experiments，再用可核實結果更新 Abstract 與 Conclusion。作者確認後補正式作者欄。
4. 透過 Overleaf 編譯並檢查 PDF、引用及版面，按驗收規格回報未解決事項。

## Risks / Trade-offs

- 投稿版面 → 依 ICEIB 2027 官網核對英文全文 4 至 8 頁。官網列出 Engineering Proceedings DOCX 範本名稱，當前公開投稿頁未提供可核對的 2027 IEEE 範本檔。正式版型依目標軌道的公開檔案確認。
- 結果或作者欄缺資料 → 保留對應待辦並在收件後核對來源，本機的構造案例繼續用於說明方法。

## 首次套用紀錄

以下記錄首次修訂與編譯時的狀態。

- 2026-11-25 已依核准的本機底稿更新 DIC4 的 `main.tex`。讀回內容核對一致，完成七個部分的重整，保留一張架構圖、一張題型表、五個編號公式及 12 筆文獻。Related Work 已補比較敘述，對照表的格式仍待正式 A-to-Z 指南確認。
- 文獻逐筆對照資料集、出版社、會議論文集、作者原文或機構出版頁。三筆 arXiv 工作依稿內列出的預印本版本核對，正文引用首次出現順序與 References 一致。
- Overleaf PDF 編譯紀錄 `1a210c8a08d-bd7edc42bda55c94` 產出 5 頁，無編譯錯誤或未解析引用。原始 log 有 4 則 underfull hbox 排版訊息。逐頁檢視確認七個部分依序出現，架構圖、題型表、公式、References 與作者占位欄均可讀。
- Abstract、Experiments 和 Conclusion 標示實測結果待補，作者欄使用占位符。正式作者資料、三類實驗結果與重現紀錄，以及老師指定的 A-to-Z 版本尚待提供。
- ICEIB 2027 官網列出英文全文 4 至 8 頁，摘要截止 2027-03-01，接受摘要的全文截止 2027-04-20。官網標示 Engineering Proceedings DOCX 範本。工作稿採 IEEEtran conference，待取得投稿軌道的正式檔案後核對。[ICEIB 2027 投稿說明](https://www.iceib.asia/#submission)

## 後續實驗與編譯紀錄

- 使用 UCI 原始 ZIP 執行逐時預測與異常篩檢。已針對 5,189 個排定測試時段重算指標，4,590 個小時的目標與三法預測都完整。Random Forest 的 MAE 為 0.321 kWh、RMSE 為 0.469 kWh、可用率 88.6%。Persistence 和 daily seasonal naive 的 MAE 分別為 0.386 和 0.504 kWh，可用率均為 95.9%。
- 異常篩檢在原始測試序列有 4,827 個小時可評分，閾值 3.5 產生 510 個高用量候選與 43 個低用量候選。保留閾值敏感度及 150 個錨點的合成注入紀錄，並檢查合成分數與原始序列候選數。主張範圍為單戶用電資料與合成變動。
- 已在 Overleaf 更新摘要、比較表、方法、實驗與結論。預測及異常結果可從逐時紀錄重算。資料與腳本 checksum、版本、參數、切分和紀錄存於 [實驗目錄說明](../../../ICEIB%20paper/experiments/README.md) 及 [結果摘要](../../../ICEIB%20paper/experiments/results/summary.json)。Agent 評估缺模型服務設定、執行及評分紀錄，維持待補。作者資料依使用者指示暫緩。
- Overleaf 編譯 `1a210d98988-9aa75ea57e3c2047` 產出 6 頁 PDF。已檢查三張新增表格、章節、圖、公式和最後一頁雙欄版面。無編譯錯誤或未解析的交叉引用及文獻，原始 log 有 4 則 underfull hbox 排版訊息。

## 主稿格式確認

- 使用者確認依 `AGENTS.md` 保留 Overleaf `main.tex` 的 `IEEEtran` Conference 格式。ICEIB 官網內嵌的 [Engineering Proceedings Word 範本](../../../ICEIB%20paper/ICEIB%202027%20Engineering%20Proceedings%20Template.docx) 已留存供該軌道查考。正式投稿如另有 ICEIB 2027 IEEE 軌道專用指引，依指引再核對。[ICEIB 2027 投稿說明](https://www.iceib.asia/#submission) · [Overleaf IEEE Conference Template](https://www.overleaf.com/latex/templates/ieee-conference-template/grfzhhncsfqn)
- `main.tex` 仍為編譯主檔。重新編譯 `1a211f321ab-2ac5c0d705f78e7d` 產出 6 頁 PDF，無編譯錯誤或未解析引用，符合官網的 4 至 8 頁要求。

## Agent 評估準備

- [實驗目錄](../../../ICEIB%20paper/experiments/README.md) 加入本機重播、配對執行、成本上限與評分彙整。從原始 UCI 資料及已核對的預測和異常紀錄重建 [10 題試測和 50 題正式候選](../../../ICEIB%20paper/experiments/agent-task-candidates.json)。答案鍵供本機評分，模型只會收到當次題目、重播時間及工具紀錄。
- 以預先定義的回應測試 300 個排程位置、A/B 共用提示與工具、一次修正、八次工具呼叫上限、失敗及逾時的覆蓋率分母，以及匿名評分與分歧處理。正式試測、A/B 成效及評分仍待雲端模型設定、費用上限與獨立評分者。
- 已在 Overleaf 的評分方法與 Agent 狀態段落記錄欄位覆蓋率分母和本機驗證進度。編譯 `1a2127fd0ea-ff39b3ff7e3374c7` 產出 6 頁 IEEE PDF。已檢查改動的第 5、6 頁，無編譯錯誤或未解析引用。原始 log 有 4 則 underfull hbox 訊息。

## 逐時紀錄補充分析與 Overleaf 更新

- 從 [`forecast-test.jsonl`](../../../ICEIB%20paper/experiments/results/forecast-test.jsonl) 逐列套用 `agent_replay.py` 的方法順序，選取第一個有值的預測：random forest、persistence、daily seasonal naive 分別選到 4,598、376、51 筆。共提供 5,025/5,189 筆預測（96.8%），164 小時缺預測。選中預測且有完整目標的 4,971 小時，MAE 為 0.329 kWh、RMSE 為 0.483 kWh。三法比較仍以共同的 4,590 小時為評分分母，並重算核對原表。
- 在 [`anomaly-observed.jsonl`](../../../ICEIB%20paper/experiments/results/anomaly-observed.jsonl) 核對 2010-04-24 22:00 的高用量案例，並以該筆用電量、歷史中位數及 MAD 重算分數 3.706。從 [`anomaly-synthetic.jsonl`](../../../ICEIB%20paper/experiments/results/anomaly-synthetic.jsonl) 對相同的 150 個錨點，分別計數原始分數不超過 3.5、注入後超過 3.5 的列。增量 0.5 和 1.0 kWh 分別新增 37 和 56 個高用量候選。
- 核對 Agent 題集的來源檔雜湊、試測與正式候選題的分層、時間邊界和題目重複情形。`run_workload` 對 50 題產生 300 個不重複的正式排程位置，每個條件 150 個。稿件依實際進度保留雲端試測、A/B 成效、評分及成本待補，作者欄維持占位。
- 更新 DIC4 的 `main.tex` 後，以 MCP 讀回核對改動，確認 12 筆文獻均可解析。編譯 `1a2129f3929-360e6ea3ec304baa` 成功生成 6 頁，無編譯錯誤或未解析引用。檢閱全部頁面的版面及第 4 至 6 頁的結果與討論。原始 log 含 4 則 underfull hbox 與 1 則 underfull vbox 排版訊息。

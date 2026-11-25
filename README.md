# DIC4｜Energy Detective 家庭用電分析研究

本專案收錄 Energy Detective 的 ICEIB 2027 英文論文、實驗程式與評估紀錄。研究探討一個問題：當使用者以自然語言詢問家庭用電時，讓 AI 助理依據工具的計算紀錄核對回答，並有一次修正機會，能否提升數值、時間與單位的正確性？

Energy Detective 支援的任務設計涵蓋歷史用電查詢、時段比較、異常篩檢、下一小時用電預測與檢查建議。實驗使用 UCI 的單戶分鐘級用電資料。每道題目設定一個歷史時間點，分析工具只能使用當時已取得的資料，回答中的數值可追溯至來源時段與計算方式。

## 從哪裡開始

| 想做的事 | 入口 |
| --- | --- |
| 閱讀論文 | [Overleaf 工作稿](https://www.overleaf.com/project/6b064ca3ec5187a86110dd8c) · [本機 LaTeX 修訂底稿](ICEIB%20paper/main.txt) |
| 了解研究動機與早期設計 | [DIC3 研究提案摘要](DIC3-ProjectRefactor/readme.md) |
| 重現實驗或檢查評分方式 | [實驗說明與執行指令](ICEIB%20paper/experiments/README.md) |
| 核對實測數據 | [結果摘要與軟體版本](ICEIB%20paper/experiments/results/summary.json) · [逐時預測與異常篩檢紀錄](ICEIB%20paper/experiments/results/) |
| 接續論文修訂 | [OpenSpec 專案結構](#openspec-專案結構) · [待辦與進度](openspec/changes/revise-iceib-paper/tasks.md) |

## 實驗進度

- **逐時預測已完成。** 已依時間順序切分資料，在三種方法皆有預測值的測試時段比較隨機森林、沿用前一小時用電量、沿用前一天同時段用電量的 MAE 與 RMSE，並另行記錄各方法的預測可用率。
- **異常篩檢已完成。** 已檢查原始觀測在不同閾值下的候選數，並在 150 個歷史時點注入指定用電增量，評估篩檢對增量的反應。原始資料缺少設備故障標籤，因此這項實驗只能評估用電偏離程度。
- **AI 助理配對評估待執行。** 已建立 10 題試測題與 50 題正式候選題。待確認雲端模型與費用上限後，先試測並凍結題集，再讓兩種條件各執行三輪，共 300 次正式任務。回答品質、人工評分與模型成本仍待實測。

## 重現預測與異常篩檢

下載 [UCI 家庭用電資料集](https://archive.ics.uci.edu/dataset/235/individual+household+electric+power+consumption) 的原始 ZIP 檔。依結果摘要中的版本準備 Python 環境，從專案根目錄執行以下 PowerShell 指令，並將第一個參數換成 ZIP 檔的實際路徑。第二個參數指定新結果的輸出目錄，方便與已提交的紀錄比對。

```powershell
python 'ICEIB paper/experiments/evaluate.py' 'C:/data/household-power.zip' './replay-results'
```

## OpenSpec 專案結構

目前的論文修訂記錄在 `openspec/changes/revise-iceib-paper/`。

```text
openspec/
├── config.yaml
├── specs/
│   └── .gitkeep
└── changes/
    ├── archive/
    │   └── .gitkeep
    └── revise-iceib-paper/
        ├── .openspec.yaml
        ├── proposal.md
        ├── design.md
        ├── tasks.md
        └── specs/
            └── iceib-manuscript/
                └── spec.md
```

| 檔案或目錄 | 用途 |
| --- | --- |
| [config.yaml](openspec/config.yaml) | 設定本專案的 OpenSpec 工作流程，目前使用 `spec-driven`。 |
| [specs/](openspec/specs/) | 存放專案現行規格，目前只有目錄保留檔。 |
| [changes/archive/](openspec/changes/archive/) | 存放已歸檔的變更，目前只有目錄保留檔。 |
| [.openspec.yaml](openspec/changes/revise-iceib-paper/.openspec.yaml) | 記錄這項變更的 OpenSpec 設定。 |
| [proposal.md](openspec/changes/revise-iceib-paper/proposal.md) | 說明論文為何修訂，以及修訂範圍。 |
| [design.md](openspec/changes/revise-iceib-paper/design.md) | 記錄章節與 A-to-Z 指南的對照、實驗設計及修訂決策。 |
| [spec.md](openspec/changes/revise-iceib-paper/specs/iceib-manuscript/spec.md) | 定義稿件結構、實驗證據及投稿格式的驗收條件。 |
| [tasks.md](openspec/changes/revise-iceib-paper/tasks.md) | 追蹤撰稿、實驗、審查與投稿準備進度。 |

接續修訂時，先查看 `proposal.md` 與 `design.md`，從 `tasks.md` 選擇待辦，並依 `spec.md` 驗收後勾選完成。撰稿依循 [專案規範](AGENTS.md) 與 [A-to-Z 寫作範例](DIC3-ProjectRefactor/myplan/A2Z%20outline%20example.pdf)。目前工作稿採 IEEEtran conference 格式，最終投稿範本與作者資料仍待確認。編輯前先核對 Overleaf 原稿與文獻，完成後編譯並檢查引用、版面及待補結果。

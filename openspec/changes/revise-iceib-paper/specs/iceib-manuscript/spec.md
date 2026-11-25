# Energy Detective ICEIB 稿件驗收規格

## Purpose

為 Energy Detective 的英文 ICEIB 稿件定義可核對的驗收標準，涵蓋現稿版本、章節對照、實驗證據、作者資訊、文獻引用與 Overleaf 編譯結果。

## ADDED Requirements

### Requirement: 修訂基於已確認的現稿

論文修訂 SHALL 在使用者確認規劃、目標 Overleaf 專案和現稿版本後開始，並沿用該版本的英文 LaTeX 內容與文獻。

#### Scenario: Overleaf 只有空白模板
- **WHEN** 目標專案的來源只有空白模板，而既有研究草稿位於本機或另一個專案
- **THEN** 規劃文件記錄兩者的差異及暫定盤點來源，Overleaf 修訂維持待確認，直到使用者確認目標與應採用的稿件

#### Scenario: 確認使用現有論文
- **WHEN** 使用者確認目標專案及應沿用的現稿
- **THEN** 透過 Overleaf MCP 重讀目標的檔案樹、主檔、引入檔案及相關文獻，並把已確認的稿件版本當作修訂基準

### Requirement: 英文章節與 A-to-Z 對照

英文稿件 SHALL 依序包含 Abstract、Introduction、Related Work、Proposed Design、Experiments、Conclusion、References，並依老師確認的 A-to-Z 指南核對各節內容。

#### Scenario: 核對指南版本
- **WHEN** 目前可取得 A-to-Z 教學範例，老師指定的版本仍未確認
- **THEN** 以範例提供暫定映射，並將受版本影響的內容、格式、表格、演算法與數學證明等要求標為待確認

#### Scenario: 核對章節搬移與內容
- **WHEN** 以 PDF 與 LaTeX 核對已修訂的稿件
- **THEN** 指定的七個部分依序出現，資料契約、Agent 架構和示例位於 Proposed Design，評估方法、實測結果和相關討論位於 Experiments，結論有研究貢獻、結果與限制的對應敘述
- **AND** 原有章節、圖表與公式於搬移後仍有有效的標籤及引用，A-to-Z 確認後的各項要求有可定位的對應段落

### Requirement: 結果可追溯到實驗紀錄

摘要、Experiments 與 Conclusion 的量化或成效主張 SHALL 追溯至實際輸出、計算方法與明確分母，並保留資料、方案和版本資訊。

#### Scenario: 回報預測結果
- **WHEN** 報告 random forest、persistence 和 daily seasonal naive 的一小時預測結果
- **THEN** 同一 chronological holdout 的共同可評估時段有三法的 MAE、RMSE（kWh）及樣本數，各法以排定測試時數為分母的可用率、目標及特徵缺值計數亦有記錄
- **AND** 分割時間、訓練截止與特徵來源可核對，空共同樣本的誤差標為未定義

#### Scenario: 回報 Agent 對照結果
- **WHEN** 比較既有評估協定的 A/B 條件
- **THEN** 可查到 10 題試測、正式題及評分規則、同條件配置與每題的執行和評分紀錄，並與稿件中的實際執行數對帳
- **AND** 以題目為配對單位彙整任務完成率，呈現各條件的證據一致性、應答欄位覆蓋、適當限制、不必要拒答、建議評分與評分者一致程度，以及延遲、工具、模型用量和可核實成本
- **AND** 包含各指標分母與失敗、逾時的處理，區間估計若有提供可追溯到題目層級的配對重抽樣

#### Scenario: 異常篩檢結果
- **WHEN** 報告異常篩檢結果
- **THEN** 回報異常測試的算例、時間隔離及閾值敏感度，並標示合成注入與原始資料案例的來源和驗證範圍

#### Scenario: 實驗結果待補
- **WHEN** 預測、Agent 或異常篩檢證據仍未取得
- **THEN** 寫明待補的證據，現稿示例照實標示為構造案例，成果主張只涵蓋可驗證的資料與對照設計

### Requirement: 作者欄和文獻可核對

IEEE 作者欄 SHALL 使用作者確認的順序、英文署名、隸屬及聯絡資料。References SHALL 包含正文依賴的可查證來源。

#### Scenario: 完成作者與引用審查
- **WHEN** 核對稿首與 References
- **THEN** 每位作者的正式英文姓名、作者順序、系所、機構、城市與國家已確認，通訊作者和投稿要求的電子郵件已確認，作者欄占位符已清除
- **AND** 文獻的作者、標題、出版狀態、年份及 DOI、連結或版本經來源核對，正文引用可解析並支持對應敘述

### Requirement: Overleaf 編譯驗收

完成修訂後的稿件 SHALL 使用經確認的 ICEIB 指定 IEEE conference 範本，並有 Overleaf 編譯與 PDF 檢查紀錄。

#### Scenario: 驗收編譯與版面
- **WHEN** 在確認的 Overleaf 專案編譯修訂稿並檢閱 PDF
- **THEN** PDF 可生成，章節文字、作者欄、公式、圖表、交叉引用與 References 可讀且無未解析引用
- **AND** 驗收紀錄列出仍存在的錯誤、警告、待補引用或占位結果，未達成的對應待辦維持未完成

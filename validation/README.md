# MLB 前瞻驗證帳本

這套帳本只接受尚未開賽的預測。預測與賽果分開寫入，兩份 JSONL 都使用 SHA-256 雜湊鏈；任何既有列被修改、刪除或換序，`verify` 都會失敗。

本帳本從下一批尚未開賽的比賽開始，不回填 2026-08-12 已完成賽事。這可避免模型看到結果後才調整輸入或分類。

## 每日流程

所有命令都在 repository 根目錄執行。

1. 複製 `validation/prediction_template.csv`，為同一時間點的候選下注與 `PASS` 決策各填一列。
2. 開賽前鎖定資料：

   ```powershell
   python work/prospective_validation.py record --input validation/inbox/2026-08-13_initial.csv
   python work/prospective_validation.py verify
   ```

3. 若先發或盤口有實質變化，另建一份 CSV，以 `lineup_confirmed` 或 `closing` 作為 `snapshot_label` 再次執行 `record`。不要修改已寫入的列。
4. 賽後複製 `validation/result_template.csv`，填入官方賽果並結算：

   ```powershell
   python work/prospective_validation.py settle --input validation/inbox/2026-08-13_results.csv
   python work/prospective_validation.py verify
   python work/prospective_validation.py report --output validation/reports/latest.md
   ```

`predictions.jsonl` 與 `settlements.jsonl` 是正式帳本，請只透過程式追加，不要用試算表直接編輯。雜湊鏈能偵測帳本內的異動；再配合 Git commit，才能對整份帳本的刪除或替換留下外部歷史。

## 預測欄位

- `snapshot_label`：建議固定使用 `initial`、`lineup_confirmed`、`closing`。
- `source_timestamp_utc`、`first_pitch_utc`：ISO-8601 且含時區，例如 `2026-08-12T23:30:00Z`。程式拒收已開賽資料及未來來源時間。
- `game_date`：以台灣時間的賽事日期填 `YYYY-MM-DD`；預測與賽果必須一致。
- `game_pk`：可填 MLB gamePk；若沒有，程式用日期與客主隊配對。
- `lineup_status`：`unknown`、`projected`、`mixed`、`confirmed`。
- `model_version`：建議填產生預測的 Git commit SHA 或固定版號。
- `market_away_win_probability`：來源沒有獨贏盤時可留空；報告仍保留模型校準，但略過該場的市場 Brier/log loss 基準。
- `away_mu`、`home_mu`：鎖定當下的模型得分均值。
- 所有機率與 EV 均填小數，例如 54.2% 填 `0.542`，6.3% EV 填 `0.063`。
- `market`：`none`、`moneyline`、`run_line`、`total`。
- `classification`：`FORMAL`、`WATCH`、`CONDITIONAL`、`CONFLICT`、`PASS`。
- `wager_id`：只有實際下注時填寫，且不得重複；同一注在其他 snapshot 的 `stake_units` 必須為 `0`。
- `stake_units`：實際下注單位；未下注候選填 `0`，用來同時保留 shadow ROI。
- `market_reference`：盤口來源與擷取依據，例如截圖檔名、莊家或網址。

每個賽事、每個 snapshot 可記多個市場候選，但模型均值、先發、盤口總分與勝率等賽事層欄位必須一致。即使當天沒有正式下注，也應以 `market=none`、`selection=NONE`、`line_kind=none`、價格／尾數／下注額皆為 `0` 記一筆 `PASS`，確保沒有選擇性漏記。

目前資金規則已寫入驗證器：1 單位為 NT$100、單注不得超過 1 單位、台灣日期每日不得超過 5 單位，且只有 `FORMAL` 可填正下注額。若只是在追蹤候選，不論分類為何都填 `stake_units=0` 並將 `wager_id` 留白。

## 台灣尾數盤填法

`line_value` 從所選方向解讀；`tail_fraction` 是尾數百分比的小數。

| 畫面盤口 | market | selection | line_value | line_kind | tail_fraction | 落在整數時 |
|---|---|---|---:|---|---:|---|
| 大 8+50 | total | OVER | 8 | plus | 0.50 | 贏一半、退一半 |
| 小 8+50 | total | UNDER | 8 | plus | 0.50 | 輸一半、退一半 |
| 大 8-50 | total | OVER | 8 | minus | 0.50 | 輸一半、退一半 |
| 小 8-50 | total | UNDER | 8 | minus | 0.50 | 贏一半、退一半 |
| 標準大 8.5 | total | OVER | 8.5 | half | 0 | 不會走水 |
| 標準小 8 | total | UNDER | 8 | flat | 0 | 走水 |
| 所選隊 -1-75 | run_line | 隊名 | -1 | minus | 0.75 | 剛好贏 1 分時輸 75%、退 25% |

香港盤賠率 `0.94` 表示贏得 0.94 單位，輸則損失 1 單位。

## 賽果與收盤欄位

一場比賽可用 `game_pk`，或用同一天的 `away`、`home`，一次結算該場所有預測。若不同候選的收盤線或價格不同，請各用其 `prediction_id` 建列；該 ID 會在 `record` 成功後輸出。

`closing_total` 與 `closing_away_win_probability` 是賽事層基準；`closing_line`、`closing_hk_price`、`closing_selection_probability` 是該候選方向的收盤資料。沒有可靠資料時留白，不要估填。`result_source` 必須記官方或可信來源。

## 觀察門檻

先累積至少 7 個完整賽事日或 100 場已結算的 game-snapshot；較穩健的第一次參數檢討點是 14 日或 200 場。報告會比較：

- 模型總分 MAE、偏差，與鎖定盤口及收盤盤口的 MAE；
- 模型與市場勝率的 Brier score、log loss、勝負方向命中率；
- 各分類的 shadow ROI、實際 ROI 與可取得的 CLV。

在達到門檻前不依單日輸贏改核心參數；只修正資料錯誤、程式錯誤或結算規則錯誤，而且要留下新 commit。

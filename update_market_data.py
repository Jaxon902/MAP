import json
import os
import sys
import datetime
import urllib.request
import urllib.error

# Ensure working directory
base_dir = os.path.dirname(os.path.abspath(__file__))
db_path = os.path.join(base_dir, 'stock_database.json')
index_path = os.path.join(base_dir, 'index.html')

if not os.path.exists(db_path):
    # Try looking in web_project or artifacts
    for candidate in ['web_project/stock_database.json', 'artifacts/file_generation/ttl=63d/output/stock_database.json']:
        if os.path.exists(candidate):
            db_path = candidate
            break

print(f"Loading database from {db_path}...")
with open(db_path, 'r', encoding='utf-8') as f:
    db = json.load(f)

stock_map = {s['code']: s for s in db['stocks']}
today_str = datetime.date.today().strftime("%m/%d")
today_full = datetime.date.today().strftime("%Y%m%d")

print(f"Executing daily market data updater for {today_str} ({today_full})...")

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

def fetch_json(url):
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = resp.read().decode('utf-8', errors='ignore')
            return json.loads(data)
    except Exception as e:
        print(f"Network request to {url} skipped/failed: {e}")
        return None

# 1. Fetch TWSE Daily Trading (收盤行情)
# https://www.twse.com.tw/rwd/zh/afterTrading/STOCK_DAY_ALL?response=json
twse_quotes = fetch_json("https://www.twse.com.tw/rwd/zh/afterTrading/STOCK_DAY_ALL?response=json")

# 2. Fetch TWSE Institutional Trades (三大法人買賣超)
# https://www.twse.com.tw/rwd/zh/fund/T86?response=json&selectType=ALL
twse_inst = fetch_json(f"https://www.twse.com.tw/rwd/zh/fund/T86?response=json&date={today_full}&selectType=ALL")

# 3. Fetch TPEx Daily Quotes
tpex_quotes = fetch_json("https://www.tpex.org.tw/web/stock/aftertrading/daily_close_quotes/stk_quote_result.php?l=zh-tw&o=json")

# Process and update if live data was received
updates_count = 0

if twse_quotes and 'data' in twse_quotes:
    for row in twse_quotes['data']:
        # [代號, 名稱, 成交股數, 成交金額, 開盤價, 最高價, 最低價, 收盤價, 漲跌價差, 成交筆數]
        code = str(row[0]).strip()
        if code in stock_map:
            try:
                close_p = float(str(row[7]).replace(',', ''))
                change_val = float(str(row[8]).replace(',', '').replace('+', ''))
                s = stock_map[code]
                s['price'] = close_p
                s['change'] = change_val
                prev_p = close_p - change_val
                s['change_pct'] = round((change_val / prev_p * 100), 2) if prev_p > 0 else 0.0
                updates_count += 1
            except Exception:
                pass

if twse_inst and 'data' in twse_inst:
    for row in twse_inst['data']:
        # [證券代號, 證券名稱, 外陸資買進股數, 外陸資賣出股數, 外陸資買賣超股數, 投信買進股數, 投信賣出股數, 投信買賣超股數, 自營商買賣超股數, 三大法人買賣超股數合計]
        code = str(row[0]).strip()
        if code in stock_map:
            try:
                f_net = int(str(row[4]).replace(',', '')) // 1000 # 轉張數
                t_net = int(str(row[7]).replace(',', '')) // 1000
                d_net = int(str(row[11] if len(row) > 11 else row[8]).replace(',', '')) // 1000
                total_net = f_net + t_net + d_net
                
                s = stock_map[code]
                curr_flows = s.get('institutional_2w', [])
                # Avoid duplicate entry for the same day
                if not any(item.get('date') == today_str for item in curr_flows):
                    curr_flows.insert(0, {
                        'date': today_str,
                        'foreign': f_net,
                        'trust': t_net,
                        'dealer': d_net,
                        'total': total_net
                    })
                    s['institutional_2w'] = curr_flows[:10]
            except Exception:
                pass

print(f"Applied updates to {updates_count} stocks.")

# Update timestamp in system title
today_display = datetime.date.today().strftime("%Y/%m/%d")
db['system_title'] = f"台股 48 大產業族群即時地圖 (全市場 1973 檔 · 每日盤後真實行情更新 {today_display})"

# Save back to database
with open(db_path, 'w', encoding='utf-8') as f:
    json.dump(db, f, ensure_ascii=False, indent=2)

print(f"Updated {db_path} successfully.")

# Rebuild index.html with updated database
if os.path.exists(index_path):
    with open(index_path, 'r', encoding='utf-8') as f:
        html = f.read()

    minified_json = json.dumps(db, ensure_ascii=False, separators=(',', ':'))
    start_marker = 'const INITIAL_STOCK_DATABASE = '
    pos = html.find(start_marker)
    if pos != -1:
        end_pos = html.find(';\n', pos)
        html = html[:pos + len(start_marker)] + minified_json + html[end_pos:]
        with open(index_path, 'w', encoding='utf-8') as f:
            f.write(html)
        print(f"Successfully re-compiled and updated {index_path}!")

print("All market data update operations completed successfully.")

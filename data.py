import math
import pandas as pd
from matplotlib import pyplot
# Load datasets
pf = pd.read_parquet("options_2025.parquet")
df = pd.read_csv("SPY ETF Stock Price History (1).csv")
dgs10 = pd.read_csv("DGS10.csv")

print(pf.columns)

# Parse dates / numerics
pf["date"] = pd.to_datetime(pf["date"], errors="coerce")
pf["expiration"] = pd.to_datetime(pf["expiration"], errors="coerce")

df["Date"] = pd.to_datetime(df["Date"], format="%m/%d/%Y", errors="coerce")
df["Price"] = pd.to_numeric(df["Price"].astype(str).str.replace(",", "", regex=False), errors="coerce")

dgs10["observation_date"] = pd.to_datetime(dgs10["observation_date"], errors="coerce")
dgs10["DGS10"] = pd.to_numeric(dgs10["DGS10"], errors="coerce")

SET_DATE = "2025-01-02"


def N(x):
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def d1(stock, strike, time_years, volatility, interest):
    numerator = math.log(stock / strike) + (interest + 0.5 * volatility * volatility) * time_years
    denominator = volatility * math.sqrt(time_years)
    return numerator / denominator


def d2(d1_value, volatility, time_years):
    return d1_value - volatility * math.sqrt(time_years)


def black_scholes_call(stock, strike, time_years, volatility, interest):
    D1 = d1(stock, strike, time_years, volatility, interest)
    D2 = d2(D1, volatility, time_years)
    return stock * N(D1) - strike * math.exp(-interest * time_years) * N(D2)


def get_underlying_on_or_before(stock_prices_by_date, expiry_date):
    exp = pd.to_datetime(expiry_date)

    if isinstance(stock_prices_by_date, dict):
        s = pd.Series(stock_prices_by_date)
        s.index = pd.to_datetime(s.index)
    else:
        s = stock_prices_by_date.copy()
        s.index = pd.to_datetime(s.index)

    s = s.sort_index()
    valid = s[s.index <= exp]
    if valid.empty:
        return None
    return float(valid.iloc[-1])


def realized_option_pnl(option_row, stock_prices_by_date):
    contract_multiplier = 100
    fees_per_contract = 0.0

    expiry_date = option_row["expiration"]
    strike = float(option_row["strike"])
    premium_paid = float(option_row["entry_price"])
    option_type = str(option_row["type"]).lower()

    S_exp = get_underlying_on_or_before(stock_prices_by_date, expiry_date)
    if S_exp is None:
        return {"status": "skip", "reason": "missing expiry underlying"}

    if option_type == "call":
        intrinsic = max(S_exp - strike, 0.0)
    elif option_type == "put":
        intrinsic = max(strike - S_exp, 0.0)
    else:
        return {"status": "skip", "reason": "unknown option type"}

    pnl_per_share = intrinsic - premium_paid
    pnl_dollars = pnl_per_share * contract_multiplier - fees_per_contract
    return_pct = pnl_per_share / premium_paid if premium_paid > 0 else None

    return {
        "status": "ok",
        "profitable": pnl_dollars > 0,
        "pnl_dollars": pnl_dollars,
        "pnl_per_share": pnl_per_share,
        "return_pct": return_pct,
        "S_exp": S_exp,
        "intrinsic_at_expiry": intrinsic,
    }


def backtest_all(options_rows, stock_prices_by_symbol_date):
    results = []
    for _, row in options_rows.iterrows():
        symbol = row["symbol"]

        if symbol not in stock_prices_by_symbol_date:
            results.append({
                "status": "skip",
                "reason": f"missing stock series for {symbol}",
                "contract_id": row.get("contract_id"),
                "symbol": symbol,
                "date": row.get("date"),
                "expiration": row.get("expiration"),
            })
            continue

        key_prices = stock_prices_by_symbol_date[symbol]
        result = realized_option_pnl(row, key_prices)

        result["contract_id"] = row.get("contract_id")
        result["symbol"] = symbol
        result["date"] = row.get("date")
        result["expiration"] = row.get("expiration")

        results.append(result)
    return results


# Single-date debug block (same style as before)
filtered_pf = pf.loc[pf["date"] == SET_DATE]
if filtered_pf.empty:
    raise ValueError(f"No rows found for date {SET_DATE}")

filterd_df = df.loc[df["Date"] == SET_DATE]
filtered_rate = dgs10.loc[dgs10["observation_date"] == SET_DATE]

if filterd_df.empty:
    raise ValueError(f"No SPY price row found for date {SET_DATE}")
if filtered_rate.empty:
    raise ValueError(f"No DGS10 row found for date {SET_DATE}")
succesful = 0
bad_trades = 0
save = 0
bad_call = 0
money_made = 0
trade_idx = []
pnl_all = []
good_buy_idx = []
good_buy_pnl = []
bad_buy_idx = []
bad_buy_pnl = []
good_skip_idx = []
good_skip_pnl = []
missed_buy_idx = []
missed_buy_pnl = []
buy_trade_idx = []
cumulative_buy_pnl = []
dates_list = pf["date"].dropna().drop_duplicates().sort_values().tolist()
backtest_candidates = []
stock_series = df.set_index("Date")["Price"].dropna()

for set_date in dates_list:
    filtered_pf = pf.loc[pf["date"] == set_date]
    filtered_df = df.loc[df["Date"] == set_date]
    filtered_rate = dgs10.loc[dgs10["observation_date"] == set_date]

    if filtered_pf.empty or filtered_df.empty or filtered_rate.empty:
        continue

    first_entry = filtered_pf.iloc[0]
    backtest_candidates.append(first_entry.copy())

    STOCK = float(filtered_df["Price"].iloc[0])
    STRIKE = float(first_entry["strike"])
    TIME = (pd.to_datetime(first_entry["expiration"]) - pd.to_datetime(first_entry["date"])).days / 365.0
    if TIME <= 0:
        TIME = 1 / 365

    VOLATILITY = float(first_entry["implied_volatility"])
    INTEREST = float(filtered_rate["DGS10"].iloc[0]) / 100.0
    OPTION = float(first_entry["ask"])

    C = black_scholes_call(STOCK, STRIKE, TIME, VOLATILITY, INTEREST)

    edge = C - OPTION
    min_edge = 0   # per share, tune this

    if pd.isna(C):
        decision = "Dont Buy"
    elif edge > min_edge:
        decision = "Buy Now"
    else:
        decision = "Dont Buy"

    option_row = first_entry.copy()
    option_row["entry_price"] = OPTION
    pnl_result = realized_option_pnl(option_row, stock_series)
    pnl_dollars = pnl_result.get("pnl_dollars")
    if pnl_dollars is None:
        continue

    print(set_date.date(), first_entry["contract_id"], "option=", OPTION, "model=", C, decision, "pnl_dollars=", pnl_dollars)
    current_idx = len(trade_idx) + 1
    trade_idx.append(current_idx)
    pnl_all.append(pnl_dollars)

    if decision == "Buy Now":
        money_made += pnl_dollars
        buy_trade_idx.append(current_idx)
        cumulative_buy_pnl.append(money_made)
   
    if decision == "Buy Now" and pnl_dollars > 0:
        succesful += 1
        good_buy_idx.append(current_idx)
        good_buy_pnl.append(pnl_dollars)
    if decision == "Buy Now" and pnl_dollars < 0:
        bad_trades += 1
        bad_buy_idx.append(current_idx)
        bad_buy_pnl.append(pnl_dollars)
    if decision == "Dont Buy" and pnl_dollars < 0:
        save += 1
        good_skip_idx.append(current_idx)
        good_skip_pnl.append(pnl_dollars)
    if decision == "Dont Buy" and pnl_dollars > 0:
        bad_call += 1
        missed_buy_idx.append(current_idx)
        missed_buy_pnl.append(pnl_dollars)
        

    


# One-row pnl check
option_row = filtered_pf.iloc[0].copy()
option_row["entry_price"] = float(option_row["ask"])
result = realized_option_pnl(option_row, stock_series)
print(f"The Actual Profit/Loss is: {result.get('pnl_dollars')}")
print(result)

# Loop over many rows (same style as before)
stock_prices_by_symbol_date = {"SPY": df.set_index("Date")["Price"].dropna()}
option_rows = pd.DataFrame(backtest_candidates)
option_rows["entry_price"] = pd.to_numeric(option_rows["ask"], errors="coerce")
option_rows = option_rows.dropna(subset=["entry_price"])

results = backtest_all(option_rows, stock_prices_by_symbol_date)

for r in results[:281]:
    print(str(r.get("date")) + " " + str(r.get("pnl_dollars")))
print("\n======== Trade Summary =========")
print(f"Made Bad Trades : {bad_trades} times")
print(f"Made Good Trades : {succesful} times")
print(f"Correctly Didnt Buy : {save} times")
print(f"Should have bought but didnt : {bad_call} times")
print(f"Money made : ${round(money_made, 5)}")
print("==================================")


# 2. Create a simple outcome chart
pyplot.style.use("seaborn-v0_8-whitegrid")
fig, (ax1, ax2) = pyplot.subplots(2, 1, figsize=(12, 8), sharex=True)

ax1.axhline(0, color="black", linewidth=1)
ax1.scatter(good_buy_idx, good_buy_pnl, color="#2ca02c", marker="^", s=70, label="Bought + Profitable")
ax1.scatter(bad_buy_idx, bad_buy_pnl, color="#d62728", marker="v", s=70, label="Bought + Loss")
ax1.scatter(good_skip_idx, good_skip_pnl, color="#1f77b4", marker="o", s=45, label="Skipped + Avoided Loss")
ax1.scatter(missed_buy_idx, missed_buy_pnl, color="#ff7f0e", marker="x", s=55, label="Skipped + Missed Profit")
ax1.set_ylabel("PnL at Expiration ($)")
ax1.set_title("Did The Strategy Buy At The Right Time?")
ax1.legend(loc="best")

total_trades = len(trade_idx)
correct_decisions = succesful + save
accuracy_pct = (100.0 * correct_decisions / total_trades) if total_trades > 0 else 0.0
ax1.text(
    0.01,
    0.97,
    f"Trades: {total_trades} | Correct decisions: {correct_decisions} ({accuracy_pct:.1f}%)",
    transform=ax1.transAxes,
    va="top",
    ha="left",
    fontsize=10,
    bbox={"facecolor": "white", "alpha": 0.85, "edgecolor": "#cccccc"},
)

ax2.plot(buy_trade_idx, cumulative_buy_pnl, color="#2ca02c", linewidth=2.0)
ax2.axhline(0, color="black", linewidth=1)
ax2.set_xlabel("Trade Number (time order)")
ax2.set_ylabel("Cumulative PnL ($)")
ax2.set_title("Cumulative PnL Of Trades The Strategy Bought")

pyplot.tight_layout()
pyplot.show()

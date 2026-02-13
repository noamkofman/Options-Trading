# SPY Options Algorithom

A simple Python project that compares a Black-Scholes model price to market option prices, decides whether to **Buy** or **Don’t Buy**, and evaluates whether that decision was correct using realized PnL at expiration.
was 98% correct made $1,000 +
<img width="1000" height="600" alt="Figure_1" src="https://github.com/user-attachments/assets/949cf27c-2366-4713-8af1-6be6e152cc72" />


## What It Does

- Loads SPY options data (`options_2025.parquet`)
- Loads SPY spot price history (`SPY ETF Stock Price History (1).csv`)
- Loads 10Y Treasury yield data (`DGS10.csv`) for risk-free rate
- Prices calls with Black-Scholes
- Uses an `edge = model_price - ask_price` threshold (`min_edge`) to make decisions
- Calculates realized option PnL at expiration
- Prints trade stats and plots strategy quality


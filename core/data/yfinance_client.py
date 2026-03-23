import yfinance as yf
import pandas as pd


class YFinanceClient:
    def fetch_ohlcv(self, symbol: str, period: str = "3mo",
                    interval: str = "1d") -> pd.DataFrame:
        ticker = yf.Ticker(symbol)
        df = ticker.history(period=period, interval=interval)
        df.columns = [c.lower() for c in df.columns]
        return df[["open", "high", "low", "close", "volume"]].dropna()

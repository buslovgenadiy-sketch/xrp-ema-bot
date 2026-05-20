   import os
import time
import requests
import pandas as pd

TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

SYMBOL = "XRPUSDT"
CATEGORY = "linear"
INTERVAL = "5"

EMA_FAST = 20
EMA_SLOW = 50

CHECK_SECONDS = 20
LOOKBACK_CANDLES = 6

BYBIT_URL = "https://api.bybit.com/v5/market/kline"

last_sent_cross_time = None


def send_message(text):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"

    data = {
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "HTML"
    }

    response = requests.post(url, data=data, timeout=10)

    print("Telegram:", response.status_code)
    print(response.text)


def get_candles():
    params = {
        "category": CATEGORY,
        "symbol": SYMBOL,
        "interval": INTERVAL,
        "limit": 200
    }

    response = requests.get(BYBIT_URL, params=params, timeout=10)

    try:
        data = response.json()
    except Exception:
        print("Bybit вернул не JSON:")
        print(response.text[:500])
        return pd.DataFrame()

    if data.get("retCode") != 0:
        print("Ошибка Bybit:")
        print(data)
        return pd.DataFrame()

    df = pd.DataFrame(
        data["result"]["list"],
        columns=[
            "time",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "turnover"
        ]
    )

    df["time"] = pd.to_datetime(df["time"].astype(int), unit="ms")

    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = df[col].astype(float)

    df = df.sort_values("time").reset_index(drop=True)

    return df


def calculate_indicators(df):
    df["ema20"] = df["close"].ewm(span=EMA_FAST, adjust=False).mean()
    df["ema50"] = df["close"].ewm(span=EMA_SLOW, adjust=False).mean()

    df["volume_avg"] = df["volume"].rolling(20).mean()

    df["tr"] = df["high"] - df["low"]
    df["atr"] = df["tr"].rolling(14).mean()

    delta = df["close"].diff()

    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()

    rs = gain / loss

    df["rsi"] = 100 - (100 / (1 + rs))

    return df


def find_last_cross(df):
    closed_df = df.iloc[:-1].copy()
    recent = closed_df.tail(LOOKBACK_CANDLES)

    crosses = []

    for i in range(1, len(recent)):
        prev = recent.iloc[i - 1]
        last = recent.iloc[i]

        long_cross = (
            prev["ema20"] <= prev["ema50"]
            and last["ema20"] > last["ema50"]
        )

        short_cross = (
            prev["ema20"] >= prev["ema50"]
            and last["ema20"] < last["ema50"]
        )

        if long_cross:
            crosses.append({
                "type": "LONG",
                "row": last,
                "time": str(last["time"])
            })

        if short_cross:
            crosses.append({
                "type": "SHORT",
                "row": last,
                "time": str(last["time"])
            })

    if len(crosses) == 0:
        return None

    return crosses[-1]


def analyze_cross(cross):
    signal_type = cross["type"]
    last = cross["row"]

    score = 0
    reasons = []

    ema_distance = abs(last["ema20"] - last["ema50"])
    atr = last["atr"]

    if atr > 0 and ema_distance > atr * 0.1:
        score += 2
        reasons.append("EMA разошлись нормально")
    else:
        reasons.append("EMA близко друг к другу")

    if last["volume"] > last["volume_avg"]:
        score += 2
        reasons.append("Объём выше среднего")
    else:
        reasons.append("Объём слабый")

    if signal_type == "LONG":
        if last["close"] > last["ema20"]:
            score += 2
            reasons.append("Цена выше EMA20")
        else:
            reasons.append("Цена не выше EMA20")

        if 45 <= last["rsi"] <= 70:
            score += 2
            reasons.append(f"RSI нормальный: {round(last['rsi'], 1)}")
        else:
            reasons.append(f"RSI неидеальный: {round(last['rsi'], 1)}")

    if signal_type == "SHORT":
        if last["close"] < last["ema20"]:
            score += 2
            reasons.append("Цена ниже EMA20")
        else:
            reasons.append("Цена не ниже EMA20")

        if 30 <= last["rsi"] <= 55:
            score += 2
            reasons.append(f"RSI нормальный: {round(last['rsi'], 1)}")
        else:
            reasons.append(f"RSI неидеальный: {round(last['rsi'], 1)}")

    candle_size = abs(last["close"] - last["open"])

    if atr > 0 and candle_size > atr * 0.3:
        score += 2
        reasons.append("Свеча с импульсом")
    else:
        reasons.append("Импульс слабый")

    if score >= 7:
        advice = "✅ Вход возможен"
    elif score >= 5:
        advice = "⚠️ Вход осторожно"
    else:
        advice = "❌ Лучше пропустить"

    emoji = "🟢" if signal_type == "LONG" else "🔴"

    message = f"""
{emoji} <b>XRPUSDT {signal_type}</b>

Найдено пересечение EMA20 и EMA50

Цена: <b>{last['close']}</b>
Таймфрейм: <b>5m</b>
Сила сигнала: <b>{score}/10</b>

<b>Анализ:</b>
• {reasons[0]}
• {reasons[1]}
• {reasons[2]}
• {reasons[3]}

<b>Совет:</b>
{advice}

Время пересечения:
{last['time']}
"""

    return message


def main():
    global last_sent_cross_time

    print("Бот запущен")

    send_message(
        "✅ XRP EMA BOT запущен. Ищу пересечения EMA20/EMA50."
    )

    while True:
        try:
            df = get_candles()

            if df.empty:
                print("Свечи не получены")
                time.sleep(CHECK_SECONDS)
                continue

            df = calculate_indicators(df)

            cross = find_last_cross(df)

            if cross is None:
                print("Пересечений нет")

            else:
                print("Найдено пересечение:", cross["type"], cross["time"])

                if cross["time"] != last_sent_cross_time:
                    message = analyze_cross(cross)

                    print("ОТПРАВЛЯЮ СИГНАЛ")

                    send_message(message)

                    last_sent_cross_time = cross["time"]

                    print("Сигнал отправлен")
                else:
                    print("Это пересечение уже отправлялось")

        except Exception as e:
            print("Ошибка:", e)

        time.sleep(CHECK_SECONDS)


if __name__ == "__main__":
    main() 

    

    
    

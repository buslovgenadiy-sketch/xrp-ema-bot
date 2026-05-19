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

CHECK_SECONDS = 10

BYBIT_URL = "https://api.bybit.com/v5/market/kline"


def send_message(text):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"

    data = {
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "HTML"
    }

    response = requests.post(url, data=data, timeout=10)
    print("Telegram:", response.status_code, response.text)


def get_candles():
    params = {
        "category": CATEGORY,
        "symbol": SYMBOL,
        "interval": INTERVAL,
        "limit": 200
    }

    response = requests.get(BYBIT_URL, params=params, timeout=10)
    data = response.json()

    if data.get("retCode") != 0:
        raise Exception(data)

    candles = data["result"]["list"]

    df = pd.DataFrame(
        candles,
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
    df["open"] = df["open"].astype(float)
    df["high"] = df["high"].astype(float)
    df["low"] = df["low"].astype(float)
    df["close"] = df["close"].astype(float)
    df["volume"] = df["volume"].astype(float)

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


def analyze_signal(df):
    prev = df.iloc[-3]
    last = df.iloc[-2]

    long_cross = prev["ema20"] <= prev["ema50"] and last["ema20"] > last["ema50"]
    short_cross = prev["ema20"] >= prev["ema50"] and last["ema20"] < last["ema50"]

    print("Проверка свечи:", last["time"])
print("EMA20 предыдущая:", prev["ema20"])
print("EMA50 предыдущая:", prev["ema50"])
print("EMA20 последняя:", last["ema20"])
print("EMA50 последняя:", last["ema50"])

if long_cross:
    print("Найдено пересечение LONG")

if short_cross:
    print("Найдено пересечение SHORT")

if not long_cross and not short_cross:
    return None

    signal_type = "LONG" if long_cross else "SHORT"

    score = 0
    reasons = []

    ema_distance = abs(last["ema20"] - last["ema50"])
    atr = last["atr"]

    if atr > 0 and ema_distance > atr * 0.1:
        score += 2
        reasons.append("EMA хорошо разошлись")
    else:
        reasons.append("EMA слишком близко — движение слабое")

    if last["volume"] > last["volume_avg"]:
        score += 2
        reasons.append("Объём выше среднего")
    else:
        reasons.append("Объём слабый")

    if signal_type == "LONG":
        if last["close"] > last["ema20"]:
            score += 2
            reasons.append("Цена выше EMA 20")

        if 45 <= last["rsi"] <= 70:
            score += 2
            reasons.append(f"RSI нормальный: {round(last['rsi'], 1)}")
        else:
            reasons.append(f"RSI неидеальный: {round(last['rsi'], 1)}")

    if signal_type == "SHORT":
        if last["close"] < last["ema20"]:
            score += 2
            reasons.append("Цена ниже EMA 20")

        if 30 <= last["rsi"] <= 55:
            score += 2
            reasons.append(f"RSI нормальный: {round(last['rsi'], 1)}")
        else:
            reasons.append(f"RSI неидеальный: {round(last['rsi'], 1)}")

    candle_size = abs(last["close"] - last["open"])

    if atr > 0 and candle_size > atr * 0.3:
        score += 2
        reasons.append("Свеча с нормальным импульсом")
    else:
        reasons.append("Свеча маленькая, импульс слабый")

    if score >= 7:
    advice = "✅ Вход возможен"

elif score >= 5:
    advice = "⚠️ Сигнал средний, вход осторожно"

else:
    advice = "❌ Сигнал слабый, лучше пропустить"

    emoji = "🟢" if signal_type == "LONG" else "🔴"

    message = f"""
{emoji} <b>XRPUSDT {signal_type}</b>

EMA 20 пересекла EMA 50

Таймфрейм: <b>5 минут</b>
Цена: <b>{last['close']}</b>
Сила сигнала: <b>{score}/10</b>

<b>Анализ:</b>
- {reasons[0]}
- {reasons[1]}
- {reasons[2]}
- {reasons[3]}

<b>Совет:</b>
{advice}

Время свечи: {last['time']}
"""

    return message


def main():
    print("Бот запущен. XRPUSDT 5m EMA 20/50")

    send_message("✅ Бот запущен. Отслеживаю XRPUSDT 5m EMA 20/50")

    last_signal_time = None

    while True:
        try:
            df = get_candles()
            df = calculate_indicators(df)

            signal = analyze_signal(df)

            if signal:
                signal_time = str(df.iloc[-1]["time"])

                if signal_time != last_signal_time:
                    send_message(signal)
                    last_signal_time = signal_time
                    print("Сигнал отправлен")
                else:
                    print("Этот сигнал уже был отправлен")
            else:
                print("Пересечения нет")

        except Exception as e:
            print("Ошибка:", e)

        time.sleep(CHECK_SECONDS)


if __name__ == "__main__":
    main()

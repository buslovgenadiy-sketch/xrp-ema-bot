import os
import requests

TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

print("TOKEN есть:", TOKEN is not None)
print("CHAT_ID:", CHAT_ID)

url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"

data = {
    "chat_id": CHAT_ID,
    "text": "🚀 Бот успешно запущен на Railway!"
}

response = requests.post(url, data=data)

print("Статус:", response.status_code)
print("Ответ Telegram:", response.text)

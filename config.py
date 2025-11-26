import os

# Получаем токен из переменных окружения (для Render)
# Если переменной нет, используем значение по умолчанию (для разработки)
BOT_TOKEN = os.getenv('BOT_TOKEN', 'YOUR_BOT_TOKEN_HERE')
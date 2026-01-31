# Используем официальный образ Python
FROM python:3.11-slim

# Устанавливаем рабочую директорию в контейнере
WORKDIR /app

# Копируем файл с зависимостями и устанавливаем их
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем исходный код бота в рабочую директорию
COPY ./bot /app/bot
COPY ./bot/main.py /app/bot/main.py

# Указываем команду для запуска бота
CMD ["python", "bot/main.py"]

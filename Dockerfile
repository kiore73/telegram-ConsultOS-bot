# Используем официальный образ Python
FROM python:3.11-slim

# Устанавливаем рабочую директорию в контейнере
WORKDIR /app

# Копируем файл с зависимостями и устанавливаем их
COPY requirements.txt .
RUN pip install --no-cache-dir --verbose -r requirements.txt

# Копируем файлы опросников
COPY аюрвед_*.txt ./

# Копируем исходный код бота в рабочую директорию
COPY ./bot /app/bot

# Указываем команду для запуска бота
CMD ["python", "-m", "bot.main"]

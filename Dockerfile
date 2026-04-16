# Используем официальный slim-образ Python
FROM python:3.11-slim

# Устанавливаем системные зависимости (если понадобится)
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
    && rm -rf /var/lib/apt/lists/*

# Создаём рабочую директорию
WORKDIR /app

# Копируем только файлы с зависимостями, чтобы кешировать слой
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем остальной код
COPY . .

# Создаём директорию для базы данных, если её ещё нет
RUN mkdir -p data

# Открываем порт (необязательно для бота, но полезно для отладки)
EXPOSE 8080

# Запуск бота
CMD ["python", "bot.py"]
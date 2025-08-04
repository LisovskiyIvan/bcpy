# Используем Python 3.13
FROM python:3.13-slim

# Устанавливаем рабочую директорию
WORKDIR /app

# Устанавливаем системные зависимости
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Копируем файлы зависимостей
COPY pyproject.toml uv.lock ./

# Устанавливаем uv для управления зависимостями
RUN pip install uv

# Создаем виртуальное окружение и устанавливаем зависимости
RUN uv venv && . .venv/bin/activate && uv pip install -r pyproject.toml

# Копируем исходный код
COPY . .

# Открываем порт для FastAPI
EXPOSE 8000

# Активируем виртуальное окружение и запускаем приложение
CMD [".venv/bin/uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
# Messenger

Веб-мессенджер на Flask с регистрацией, личными чатами, вложениями и голосовыми сообщениями.

## Локальный запуск

1. Установите Python 3.11 или новее.
2. Создайте виртуальное окружение и установите зависимости:

```bash
python -m venv .venv
# Windows:
.venv\\Scripts\\activate
# macOS/Linux:
source .venv/bin/activate
pip install -r requirements.txt
```

3. Скопируйте `.env.example` в `.env` и заполните значения.
4. Запустите приложение:

```bash
flask --app index run --debug
```

## Переменные окружения

- `SECRET_KEY` — длинный случайный секрет Flask.
- `DATABASE_URL` — PostgreSQL connection string (Supabase Session Pooler, SSL).
- `SUPABASE_URL` — URL проекта Supabase.
- `SUPABASE_SERVICE_ROLE_KEY` — серверный ключ Supabase; не публикуйте и не добавляйте в Git.
- `SUPABASE_STORAGE_BUCKET` — имя бакета для файлов; по умолчанию `uploads`.

Создайте в Supabase Storage бакет с именем, указанным в `SUPABASE_STORAGE_BUCKET`.

## Голосовые сообщения

Запись использует браузерные `MediaRecorder` и `getUserMedia`. Для доступа к микрофону сайт должен работать по HTTPS (или на localhost), и пользователь должен разрешить доступ к микрофону.

## Деплой на Vercel

Проект содержит `vercel.json`. Укажите корневую папку проекта как корень репозитория и добавьте перечисленные выше переменные окружения в настройках Vercel. После изменения переменных выполните новый деплой.

**Без настроенного PostgreSQL и Supabase регистрация, постоянное хранение сообщений и загрузка голосовых работать не будут.**

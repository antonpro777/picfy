# Pixel

Социальная платформа на Flask + PostgreSQL/Supabase.

## Первая версия
- Регистрация с подтверждением email шестизначным кодом.
- Поиск по username, профили, подписки и подписчики.
- Лента публикаций, фото и видео, лайки и комментарии.
- Личные чаты с поддержкой emoji.

## Настройка
1. Установить Python 3.11+ и выполнить pip install -r requirements.txt.
2. Выполнить SQL из migrations/001_pixel_social.sql в Supabase SQL Editor.
3. Создать Storage bucket uploads.
4. Настроить переменные окружения: SECRET_KEY, DATABASE_URL, SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, SUPABASE_STORAGE_BUCKET, SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, SMTP_FROM.
5. Развернуть на Vercel.

## Важно
Сборка пока не production-ready. Текущий upload endpoint ограничен 20 МБ, а serverless-платформа может иметь более низкий лимит тела запроса. Для длинных видео нужна прямая resumable-загрузка в Storage. Голосовая запись и полноценный каталог стикеров — следующий этап. Настрой RLS и политики доступа перед публичным запуском. Service role key хранить только в серверных переменных окружения.

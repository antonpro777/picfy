# Pixel

Социальная платформа на Flask + PostgreSQL/Supabase.

## Реализовано в первой сборке
- Регистрация с подтверждением email шестизначным кодом.
- Поиск по username, профили, подписки и счётчики подписчиков.
- Лента публикаций, фото и видео, лайки и комментарии.
- Личные чаты, emoji и голосовые сообщения.
- Прямая resumable-загрузка медиа в Supabase Storage через TUS.

## Настройка
1. Установить Python 3.11+ и выполнить pip install -r requirements.txt.
2. Проверить RLS в Supabase и применить SQL из migrations/001_pixel_social.sql.
3. Создать Storage bucket uploads (для текущего варианта нужен public bucket; перед production лучше перейти на private bucket + signed read URLs).
4. Настроить переменные окружения: SECRET_KEY, DATABASE_URL, SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, SUPABASE_STORAGE_BUCKET, SMTP_HOST, SMTP_PORT (465 или 587), SMTP_USER, SMTP_PASSWORD, SMTP_FROM.
5. Развернуть на Vercel.

## Важно
Новые аккаунты требуют подтверждения почты. Старые аккаунты сохраняют возможность входа после миграции, но должны быть дополнены email при необходимости.
Service role key хранить только в серверных переменных окружения, никогда не добавлять во frontend или Git.
До публичного запуска проверь RLS на всех таблицах и настрой доступ. Для пользовательского контента добавь жалобы, модерацию, лимиты публикаций и защиту от спама.

#!/bin/bash
# Скрипт для исправления проблем с правами доступа на сервере AMVERA

echo "🔧 Исправление прав доступа..."

# Проверяем текущую директорию
CURRENT_DIR=$(pwd)
echo "📁 Текущая директория: $CURRENT_DIR"

# Устанавливаем правильные права на директорию
chmod 755 "$CURRENT_DIR"
echo "✅ Права на директорию установлены"

# Устанавливаем права на базу данных
if [ -f "bot_database.db" ]; then
    chmod 644 bot_database.db
    echo "✅ Права на базу данных установлены"
else
    echo "❌ Файл bot_database.db не найден"
fi

# Проверяем владельца файлов
echo "👤 Текущий пользователь: $(whoami)"
echo "👥 Группа: $(id -gn)"

# Устанавливаем владельца (если нужно)
# sudo chown $(whoami):$(id -gn) bot_database.db

echo "🔍 Проверка прав доступа:"
ls -la bot_database.db 2>/dev/null || echo "Файл не найден"

echo "✅ Исправление завершено"

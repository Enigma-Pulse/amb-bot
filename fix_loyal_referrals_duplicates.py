#!/usr/bin/env python3
"""
Скрипт для исправления дублирования преданных рефералов
Запускать только один раз для исправления существующих данных
"""

import sqlite3
import os
from datetime import datetime, timedelta
from config import DB_PATH, logger

def fix_loyal_referrals_duplicates():
    """Исправляет дублирование преданных рефералов"""
    
    # Подключаемся к базе данных
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        # Создаем таблицу отслеживания если её нет
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS loyal_referrals_tracking (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                referrer_id INTEGER,
                referral_id INTEGER,
                credited_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(referrer_id, referral_id),
                FOREIGN KEY(referrer_id) REFERENCES users(user_id),
                FOREIGN KEY(referral_id) REFERENCES users(user_id)
            )
        ''')
        
        # Находим всех рефералов старше 3 дней
        three_days_ago = datetime.now() - timedelta(days=3)
        
        cursor.execute("""
            SELECT u.user_id, u.username, u.ref_by, u.joined_date
            FROM users u
            WHERE u.ref_by IS NOT NULL 
            AND u.joined_date < ?
            ORDER BY u.joined_date DESC
        """, (three_days_ago.isoformat(),))
        
        old_referrals = cursor.fetchall()
        
        print(f"Найдено {len(old_referrals)} рефералов старше 3 дней")
        
        # Получаем текущие данные о преданных рефералах
        cursor.execute("""
            SELECT user_id, loyal_referrals, referrals_count
            FROM users 
            WHERE loyal_referrals > 0 OR referrals_count > 0
        """)
        
        users_with_referrals = cursor.fetchall()
        print(f"Пользователей с рефералами: {len(users_with_referrals)}")
        
        # Показываем текущее состояние
        print("\n=== ТЕКУЩЕЕ СОСТОЯНИЕ ===")
        for user_id, loyal_referrals, referrals_count in users_with_referrals:
            print(f"Пользователь {user_id}: преданных {loyal_referrals}, всего рефералов {referrals_count}")
        
        # Создаем временную таблицу для подсчета реальных преданных рефералов
        cursor.execute("""
            CREATE TEMPORARY TABLE temp_loyal_count AS
            SELECT ref_by, COUNT(*) as real_loyal_count
            FROM users 
            WHERE ref_by IS NOT NULL 
            AND joined_date < ?
            GROUP BY ref_by
        """, (three_days_ago.isoformat(),))
        
        # Обновляем счетчики преданных рефералов на основе реальных данных
        cursor.execute("""
            UPDATE users 
            SET loyal_referrals = (
                SELECT real_loyal_count 
                FROM temp_loyal_count 
                WHERE temp_loyal_count.ref_by = users.user_id
            )
            WHERE user_id IN (SELECT ref_by FROM temp_loyal_count)
        """)
        
        # Устанавливаем 0 для тех, у кого нет преданных рефералов
        cursor.execute("""
            UPDATE users 
            SET loyal_referrals = 0
            WHERE user_id NOT IN (SELECT ref_by FROM temp_loyal_count)
            AND loyal_referrals > 0
        """)
        
        # Добавляем записи в таблицу отслеживания для всех существующих преданных рефералов
        cursor.execute("""
            INSERT OR IGNORE INTO loyal_referrals_tracking (referrer_id, referral_id)
            SELECT ref_by, user_id
            FROM users 
            WHERE ref_by IS NOT NULL 
            AND joined_date < ?
        """, (three_days_ago.isoformat(),))
        
        conn.commit()
        
        # Показываем результат
        cursor.execute("""
            SELECT user_id, loyal_referrals, referrals_count
            FROM users 
            WHERE loyal_referrals > 0 OR referrals_count > 0
        """)
        
        fixed_users = cursor.fetchall()
        
        print("\n=== ИСПРАВЛЕННОЕ СОСТОЯНИЕ ===")
        for user_id, loyal_referrals, referrals_count in fixed_users:
            print(f"Пользователь {user_id}: преданных {loyal_referrals}, всего рефералов {referrals_count}")
        
        # Показываем статистику отслеживания
        cursor.execute("SELECT COUNT(*) FROM loyal_referrals_tracking")
        tracking_count = cursor.fetchone()[0]
        print(f"\nЗаписей в таблице отслеживания: {tracking_count}")
        
        print("\n✅ Исправление завершено!")
        print("Теперь система будет корректно отслеживать преданных рефералов")
        
    except Exception as e:
        print(f"Ошибка: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    print("🔧 Исправление дублирования преданных рефералов...")
    fix_loyal_referrals_duplicates() 
#!/usr/bin/env python3
"""
Скрипт для тестирования новой логики преданных рефералов
"""

import sqlite3
from datetime import datetime, timedelta
from config import DB_PATH

def test_loyal_referrals_logic():
    """Тестирует новую логику преданных рефералов"""
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
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
        
        # Создаем словарь для подсчета реальных преданных рефералов
        real_loyal_counts = {}
        
        for user_id, username, ref_by, joined_date in old_referrals:
            # В реальном боте здесь была бы проверка подписки
            # Для теста считаем всех как подписанных
            if ref_by not in real_loyal_counts:
                real_loyal_counts[ref_by] = 0
            real_loyal_counts[ref_by] += 1
        
        print(f"\nРеальных преданных рефералов: {sum(real_loyal_counts.values())}")
        
        # Показываем как будет работать новая логика
        print("\n=== ТЕСТ НОВОЙ ЛОГИКИ ===")
        
        for ref_by, real_loyal_count in real_loyal_counts.items():
            cursor.execute("""
                SELECT loyal_referrals, used_loyal FROM users WHERE user_id = ?
            """, (ref_by,))
            result = cursor.fetchone()
            
            if result:
                current_loyal, used_loyal = result
                used_loyal = used_loyal or 0
                
                # Новая логика: реальные преданные - потраченные
                new_loyal_referrals = max(0, real_loyal_count - used_loyal)
                
                print(f"Пользователь {ref_by}:")
                print(f"  - Реальных преданных: {real_loyal_count}")
                print(f"  - Потрачено: {used_loyal}")
                print(f"  - Текущий баланс: {current_loyal}")
                print(f"  - Новый баланс: {new_loyal_referrals}")
                print(f"  - Изменение: {new_loyal_referrals - current_loyal}")
                print()
        
        # Показываем пользователей с потраченными рефералами
        cursor.execute("""
            SELECT user_id, loyal_referrals, used_loyal, referrals_count
            FROM users 
            WHERE used_loyal > 0
            ORDER BY used_loyal DESC
        """)
        
        users_with_used = cursor.fetchall()
        
        if users_with_used:
            print("=== ПОЛЬЗОВАТЕЛИ С ПОТРАЧЕННЫМИ РЕФЕРАЛАМИ ===")
            for user_id, loyal_referrals, used_loyal, referrals_count in users_with_used:
                print(f"Пользователь {user_id}:")
                print(f"  - Преданных: {loyal_referrals}")
                print(f"  - Потрачено: {used_loyal}")
                print(f"  - Всего рефералов: {referrals_count}")
                print()
        
    except Exception as e:
        print(f"Ошибка: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    print("🧪 Тестирование новой логики преданных рефералов...")
    test_loyal_referrals_logic() 
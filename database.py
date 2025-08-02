import sqlite3
import os
import string
import random
from datetime import datetime
from config import DB_PATH, logger

class Database:
    def __init__(self):
        try:
            # Проверяем, существует ли директория для БД
            db_dir = os.path.dirname(DB_PATH)
            if db_dir and not os.path.exists(db_dir):
                os.makedirs(db_dir, exist_ok=True)
                logger.info(f"Created directory for database: {db_dir}")
            
            # Подключаемся к БД с улучшенными настройками
            self.conn = sqlite3.connect(DB_PATH, check_same_thread=False)
            self.cursor = self.conn.cursor()
            
            # Включаем WAL режим для лучшей производительности и надежности
            self.cursor.execute("PRAGMA journal_mode=WAL")
            self.cursor.execute("PRAGMA synchronous=NORMAL")
            self.cursor.execute("PRAGMA cache_size=10000")
            self.cursor.execute("PRAGMA temp_store=MEMORY")
            
            logger.info(f"Database connected successfully: {DB_PATH}")
            self.init_database()
            
        except Exception as e:
            logger.error(f"Failed to initialize database: {e}")
            raise
    
    def init_database(self):
        """Инициализация базы данных и создание таблиц"""
        # Создание таблицы пользователей
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                ref_by INTEGER
            )
        ''')
        
        # Создание таблицы заданий
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS tasks (
                task_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                task_description TEXT,
                status TEXT DEFAULT 'pending',
                task_type TEXT,
                screenshot_path TEXT,
                created_at TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(user_id)
            )
        ''')
        
        # Создание таблицы купонов
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS coupons (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT,
                type TEXT,
                used INTEGER DEFAULT 0
            )
        ''')
        
        # Создание таблицы шаблонов мемов
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS meme_templates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_path TEXT,
                text TEXT
            )
        ''')
        
        # Создание таблицы текстовых шаблонов
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS text_templates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                text TEXT
            )
        ''')
        
        # Создание таблицы разрешенных чатов
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS allowed_chats (
                chat_username TEXT PRIMARY KEY
            )
        ''')
        
        # Создание таблицы промо-офферов
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS promo_offers (
                offer_id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                cost INTEGER NOT NULL
            )
        ''')
        
        self.conn.commit()
        self.run_migrations()
    
    def run_migrations(self):
        """Выполнение миграций базы данных"""
        # Проверяем существующие колонки в таблице users
        self.cursor.execute("PRAGMA table_info(users)")
        cols = [row[1] for row in self.cursor.fetchall()]
        
        # Добавляем недостающие колонки
        migrations = [
            ("promo_code", "TEXT"),
            ("referrals_count", "INTEGER DEFAULT 0"),
            ("joined_date", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"),
            ("used_loyal", "INTEGER DEFAULT 0"),
            ("loyal_referrals", "INTEGER DEFAULT 0"),
            ("pending_tasks", "INTEGER DEFAULT 0"),
            ("completed_tasks", "INTEGER DEFAULT 0")
        ]
        
        for column, definition in migrations:
            if column not in cols:
                try:
                    self.cursor.execute(f"ALTER TABLE users ADD COLUMN {column} {definition}")
                    logger.info(f"Added column {column} to users table")
                except sqlite3.OperationalError as e:
                    logger.warning(f"Column {column} already exists: {e}")
        
        # Создаем уникальный индекс на promo_code
        self.cursor.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_users_promo_code
              ON users(promo_code)
        """)
        
        # Генерируем промокоды для пользователей без них
        self.cursor.execute("SELECT user_id FROM users WHERE promo_code IS NULL")
        rows = self.cursor.fetchall()
        for (uid,) in rows:
            code = self.generate_promo_code()
            self.cursor.execute(
                "UPDATE users SET promo_code = ? WHERE user_id = ?",
                (code, uid)
            )
        
        self.conn.commit()
    
    def generate_promo_code(self):
        """Генерация уникального промокода"""
        while True:
            code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
            self.cursor.execute("SELECT user_id FROM users WHERE promo_code = ?", (code,))
            if not self.cursor.fetchone():
                return code
    
    def get_or_create_user(self, user_id, username=None, first_name=None, last_name=None, ref_by=None):
        """Получение или создание пользователя с улучшенной обработкой ошибок"""
        try:
            self.cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
            user = self.cursor.fetchone()
            
            if user is None:
                # Создаем нового пользователя
                promo_code = self.generate_promo_code()
                now = datetime.now().isoformat()
                
                self.cursor.execute(
                    "INSERT INTO users (user_id, username, first_name, last_name, ref_by, promo_code, joined_date) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (user_id, username, first_name, last_name, ref_by, promo_code, now)
                )
                self.conn.commit()
                
                logger.info(f"Created new user: {user_id} (@{username or 'нет'})")
                return promo_code
            else:
                # Обновляем существующего пользователя если нужно
                if ref_by is not None and user[4] is None:  # user[4] = ref_by
                    self.cursor.execute(
                        "UPDATE users SET ref_by = ? WHERE user_id = ?",
                        (ref_by, user_id)
                    )
                    self.conn.commit()
                    logger.info(f"Updated user {user_id} with referrer {ref_by}")
                
                return user[5]  # user[5] = promo_code
                
        except Exception as e:
            logger.error(f"Error in get_or_create_user for {user_id}: {e}")
            # Пытаемся откатить транзакцию
            try:
                self.conn.rollback()
            except:
                pass
            raise
    
    def get_user_stats(self, user_id):
        """Получение статистики пользователя"""
        self.cursor.execute("""
            SELECT 
                u.promo_code,
                u.referrals_count,
                u.loyal_referrals,
                u.used_loyal,
                u.pending_tasks,
                u.completed_tasks,
                COUNT(t.task_id) as total_tasks
            FROM users u
            LEFT JOIN tasks t ON u.user_id = t.user_id
            WHERE u.user_id = ?
            GROUP BY u.user_id
        """, (user_id,))
        
        row = self.cursor.fetchone()
        if row:
            return {
                'promo_code': row[0],
                'referrals_count': row[1],
                'loyal_referrals': row[2],
                'used_loyal': row[3],
                'pending_tasks': row[4],
                'completed_tasks': row[5],
                'total_tasks': row[6]
            }
        return None
    
    def create_task(self, user_id, task_type, task_description):
        """Создание нового задания"""
        now = datetime.now()
        self.cursor.execute(
            "INSERT INTO tasks (user_id, task_type, task_description, created_at) "
            "VALUES (?, ?, ?, ?)",
            (user_id, task_type, task_description, now)
        )
        task_id = self.cursor.lastrowid
        
        # Увеличиваем счетчик ожидающих заданий
        self.cursor.execute(
            "UPDATE users SET pending_tasks = pending_tasks + 1 WHERE user_id = ?",
            (user_id,)
        )
        
        self.conn.commit()
        return task_id
    
    def approve_task(self, task_id, user_id):
        """Одобрение задания"""
        self.cursor.execute("UPDATE tasks SET status='approved' WHERE task_id = ?", (task_id,))
        self.cursor.execute(
            "UPDATE users SET pending_tasks = pending_tasks - 1, completed_tasks = completed_tasks + 1 "
            "WHERE user_id = ?", (user_id,)
        )
        self.conn.commit()
    
    def decline_task(self, task_id, user_id):
        """Отклонение задания"""
        self.cursor.execute("UPDATE tasks SET status='declined' WHERE task_id = ?", (task_id,))
        self.cursor.execute(
            "UPDATE users SET pending_tasks = pending_tasks - 1 WHERE user_id = ?", (user_id,)
        )
        self.conn.commit()
    
    def cancel_task(self, user_id):
        """Отмена последнего задания пользователя"""
        # Находим последнее ожидающее задание пользователя
        self.cursor.execute(
            "SELECT task_id FROM tasks WHERE user_id = ? AND status = 'pending' ORDER BY created_at DESC LIMIT 1",
            (user_id,)
        )
        row = self.cursor.fetchone()
        if row:
            task_id = row[0]
            # Удаляем задание и уменьшаем счетчик
            self.cursor.execute("DELETE FROM tasks WHERE task_id = ?", (task_id,))
            self.cursor.execute(
                "UPDATE users SET pending_tasks = pending_tasks - 1 WHERE user_id = ? AND pending_tasks > 0",
                (user_id,)
            )
            self.conn.commit()
            return True
        return False
    
    def get_random_meme(self):
        """Получение случайного мема"""
        self.cursor.execute("SELECT id, file_path FROM meme_templates ORDER BY RANDOM() LIMIT 1")
        return self.cursor.fetchone()
    
    def delete_meme(self, meme_id):
        """Удаление мема по ID"""
        # Получаем путь к файлу перед удалением
        self.cursor.execute("SELECT file_path FROM meme_templates WHERE id = ?", (meme_id,))
        row = self.cursor.fetchone()
        if not row:
            return False
        
        file_path = row[0]
        
        # Удаляем запись из базы данных
        self.cursor.execute("DELETE FROM meme_templates WHERE id = ?", (meme_id,))
        
        # Пытаемся удалить файл
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
        except Exception as e:
            logger.warning(f"Не удалось удалить файл {file_path}: {e}")
        
        self.conn.commit()
        return True
    
    def get_random_text(self):
        """Получение случайного текста"""
        self.cursor.execute("SELECT id, text FROM text_templates ORDER BY RANDOM() LIMIT 1")
        return self.cursor.fetchone()
    
    def get_random_chats(self, limit=5):
        """Получение случайных чатов"""
        self.cursor.execute("SELECT chat_username FROM allowed_chats ORDER BY RANDOM() LIMIT ?", (limit,))
        return [row[0] for row in self.cursor.fetchall()]
    
    def get_pending_tasks(self):
        """Получение ожидающих заданий"""
        self.cursor.execute("""
            SELECT task_id, user_id, screenshot_path, created_at 
            FROM tasks 
            WHERE status='pending' AND screenshot_path IS NOT NULL 
            ORDER BY created_at ASC LIMIT 1
        """)
        return self.cursor.fetchone()
    
    def get_all_users(self):
        """Получение всех пользователей"""
        self.cursor.execute("SELECT user_id FROM users")
        return [row[0] for row in self.cursor.fetchall()]
    
    def get_user_by_username(self, username):
        """Получение пользователя по username"""
        self.cursor.execute("SELECT user_id FROM users WHERE username = ?", (username,))
        row = self.cursor.fetchone()
        return row[0] if row else None
    
    def get_user_by_promo_code(self, promo_code):
        """Получение пользователя по промокоду"""
        self.cursor.execute("SELECT user_id FROM users WHERE promo_code = ?", (promo_code,))
        row = self.cursor.fetchone()
        return row[0] if row else None
    
    def update_screenshot_path(self, task_id, screenshot_path):
        """Обновление пути к скриншоту"""
        self.cursor.execute(
            "UPDATE tasks SET screenshot_path = ?, status = 'awaiting_review' WHERE task_id = ?",
            (screenshot_path, task_id)
        )
        self.conn.commit()
    
    def close(self):
        """Закрытие соединения с базой данных"""
        self.conn.close()

# Глобальный экземпляр базы данных
db = Database() 
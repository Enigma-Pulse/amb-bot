import logging
import sqlite3
import os
import csv
import string
import random
from datetime import datetime, timedelta
from urllib.parse import urlparse, parse_qs
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    KeyboardButton,
    Document
)
from telegram.constants import ParseMode, ChatType
from telegram.error import BadRequest
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    MessageHandler,
    filters,
    ConversationHandler,
    JobQueue
)

# Helper to notify a user of a new simple referral
async def notify_simple_referral(context: ContextTypes.DEFAULT_TYPE, user_id: int) -> None:
    await context.bot.send_message(
        chat_id=user_id,
        text="🔔<b>+1 реферал у тебя появился</b>\n😏Станет ли он преданным⁉️",
        parse_mode=ParseMode.HTML
    )

# Broadcast helpers
def reset_broadcast_state(context):
    for key in ['broadcast_stage', 'broadcast_mode', 'broadcast_text', 'broadcast_photo']:
        context.user_data.pop(key, None)

async def broadcast_panel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.delete()
    keyboard = [
        [
            InlineKeyboardButton("Всем", callback_data='broadcast_all'),
            InlineKeyboardButton("Пользователю", callback_data='broadcast_user')
        ],
        [InlineKeyboardButton("🔙 Назад", callback_data='task_back')],
        [InlineKeyboardButton("❌ Отмена", callback_data='bc_cancel')]
    ]
    await update.message.reply_text(
        "Выберите режим рассылки:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def credit_loyal_referral(context: ContextTypes.DEFAULT_TYPE) -> None:
    job = context.job
    referrer_id = job.chat_id
    referral_id = job.data
    try:
        member = await context.bot.get_chat_member(chat_id=CHANNEL_ID, user_id=referral_id)
        if member.status in ('member', 'creator', 'administrator'):
            cursor.execute(
                "UPDATE users SET loyal_referrals = loyal_referrals + 1 WHERE user_id = ?",
                (referrer_id,)
            )
            conn.commit()
            await context.bot.send_message(
                chat_id=referrer_id,
                text=(
                    "🎉<b>ТВОЙ РЕФЕРАЛ СТАЛ ПРЕДАННЫМ💖</b>\n"
                    "<b>➖Посмотри в профиле, хватает ли тебе на промо⁉️</b>"
                ),
                parse_mode=ParseMode.HTML
            )
    except Exception as e:
        logger.error(f"Error crediting loyal referral for {referrer_id}/{referral_id}: {e}")

# ——— Обработчик отложенного напоминания о реферале ———
async def send_referral_reminder(context: ContextTypes.DEFAULT_TYPE) -> None:
    job = context.job
    user_id = job.chat_id
    # шлём картинку и маркетинговый текст
    with open(REMINDER_IMAGE_PATH, "rb") as photo:
        await context.bot.send_photo(
            chat_id=user_id,
            photo=photo,
            caption=(
                "⏱ <b>Ждать 3 дня? Зачем?</b>\n"
                "Промо можно взять <b>прямо сейчас</b>:\n\n"
                '<a href="https://t.me/Kicksheringboss_bot?start=start">Жми сюда</a>'
            ),
            parse_mode=ParseMode.HTML
        )

# ID of the private channel (bot must be admin)
CHANNEL_ID = -1002090905218

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

TOKEN = "8284588833:AAGmxhM-yggPhmAupV6kfEKIJ2Q3OJYuhRU"
ADMIN_IDS = [6798547914]  # Admin user ID

# Global rules text
rules_text = (
    "<b>🛴Как это работает?</b>\n\n"
    "<b>Всё просто:</b>\n\n"
    "<i>1️⃣ Пригласил друга по своей ссылке</i>\n"
    "<i>2️⃣ Друг подписался и остался в канале 3 дня</i>\n"
    "<i>3️⃣ Получил балл, баллы = реальные купоны</i>\n\n"
    "<b>📌Куда звать людей?</b>\n\n"
    "— <i>Закидывай готовые мемы и тексты в чаты</i>\n"
    "— <i>Делись ссылкой с друзьями лично или в сторис</i>\n\n"
    "🤔<b>Не умеешь приглашать?</b>\n"
    "<b>Бот поможет и подскажет, что делать.</b>\n\n"
    "<b>🚀Больше друзей — больше промокодов!</b>"
)

# Database setup
BASE_DIR = os.environ.get("BASE_DIR", os.path.dirname(__file__))
DB_PATH = os.environ.get("DB_PATH", os.path.join(BASE_DIR, "bot_database.db"))
conn = sqlite3.connect(DB_PATH, check_same_thread=False)
cursor = conn.cursor()
REMINDER_IMAGE_PATH = os.path.join(BASE_DIR, "reminder.png")
WELCOME_IMAGE_PATH = os.path.join(BASE_DIR, "welcome.jpg")

STATIC_DIR = os.environ.get("STATIC_DIR", BASE_DIR)
MEMES_DIR = os.path.join(BASE_DIR, "memes")
SCREENSHOTS_DIR = os.path.join(BASE_DIR, "screenshots")


cursor.execute('''
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    first_name TEXT,
    last_name TEXT,
    ref_by INTEGER
)
''')

# ——— Миграция: проверяем и добавляем недостающие колонки в users ———
cursor.execute("PRAGMA table_info(users)")
cols = [row[1] for row in cursor.fetchall()]

# promo_code
if 'promo_code' not in cols:
    cursor.execute("ALTER TABLE users ADD COLUMN promo_code TEXT")

# referrals_count
if 'referrals_count' not in cols:
    cursor.execute("ALTER TABLE users ADD COLUMN referrals_count INTEGER DEFAULT 0")

conn.commit()

# Уникальный индекс на promo_code
cursor.execute("""
    CREATE UNIQUE INDEX IF NOT EXISTS idx_users_promo_code
      ON users(promo_code)
""")
conn.commit()

# ### 2.1. Берём всех, у кого promo_code IS NULL
cursor.execute("SELECT user_id FROM users WHERE promo_code IS NULL")
rows = cursor.fetchall()
for (uid,) in rows:
    # Генерируем 6 символов из A–Z и 0–9
    code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    cursor.execute(
        "UPDATE users SET promo_code = ? WHERE user_id = ?",
        (code, uid)
    )
conn.commit()

# Ensure joined_date and used_loyal columns exist
for column, definition in [
    ("joined_date", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"),
    ("used_loyal", "INTEGER DEFAULT 0"),
]:
    try:
        cursor.execute(f"ALTER TABLE users ADD COLUMN {column} {definition}")
    except sqlite3.OperationalError:
        # Column already exists
        pass
conn.commit()

# Add column to permanently track earned loyal referrals
try:
    cursor.execute("ALTER TABLE users ADD COLUMN loyal_referrals INTEGER DEFAULT 0")
except sqlite3.OperationalError:
    pass
conn.commit()

cursor.execute('''
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

cursor.execute('''
CREATE TABLE IF NOT EXISTS coupons (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT,
    type TEXT,
    used INTEGER DEFAULT 0
)
''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS meme_templates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_path TEXT,
    text TEXT
)
''')
cursor.execute('''
CREATE TABLE IF NOT EXISTS text_templates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    text TEXT
)
''')

cursor.execute('''
CREATE TABLE IF NOT EXISTS allowed_chats (
    chat_username TEXT PRIMARY KEY
)
''')

# --- PROMO OFFERS TABLE ---
cursor.execute('''
CREATE TABLE IF NOT EXISTS promo_offers (
    offer_id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    cost INTEGER NOT NULL
)
''')
conn.commit()

try:
    cursor.execute("ALTER TABLE users ADD COLUMN pending_tasks INTEGER DEFAULT 0")
except sqlite3.OperationalError:
    pass
try:
    cursor.execute("ALTER TABLE users ADD COLUMN completed_tasks INTEGER DEFAULT 0")
except sqlite3.OperationalError:
    pass
conn.commit()

inline_participate_markup = InlineKeyboardMarkup(
    [[InlineKeyboardButton("🚀 Участвовать", callback_data='participate')]]
)

# Back button markup for use in profile, rules, support, etc.
back_inline_markup = InlineKeyboardMarkup(
    [[InlineKeyboardButton("🔙 Назад", callback_data='task_back')]]
)

keyboard = [
    [InlineKeyboardButton("🚀 Участвовать", callback_data='participate')],
    [InlineKeyboardButton("👤 Профиль", callback_data='profile')],
    [InlineKeyboardButton("ℹ️ Правила", callback_data='rules')],
    [InlineKeyboardButton("🛠 Поддержка", callback_data='support')],
]

reply_markup = InlineKeyboardMarkup(keyboard)

# States for admin broadcast flow
BROADCAST_STAGE_TEXT = 'await_text'
BROADCAST_STAGE_PHOTO = 'await_photo'
BROADCAST_STAGE_CONFIRM = 'await_confirm'


# States for admin content flow
CONTENT_STAGE_ADD_MEME     = 'add_meme'
CONTENT_STAGE_MEME_CAPTION = 'meme_caption'
CONTENT_STAGE_DELETE_MEME  = 'delete_meme'
CONTENT_STAGE_ADD_TEXT     = 'add_text'
CONTENT_STAGE_LIST_TEXTS   = 'list_texts'
CONTENT_STAGE_LIST_CHATS   = 'list_chats'
CONTENT_STAGE_ADD_CHAT     = 'add_chat'
CONTENT_STAGE_DELETE_CHAT  = 'delete_chat'

# States for admin promo offers flow
PROMO_STAGE_ADD    = 'add_offer'
PROMO_STAGE_DELETE = 'delete_offer'

# ——— Утилита для нормализации chat-URL ———
def make_chat_url(raw: str) -> str:
    raw = raw.strip()
    # Если уже полный URL — оставляем как есть
    if raw.startswith(('http://', 'https://')):
        return raw
    # Если без схемы, но начинается с t.me/
    if raw.startswith('t.me/'):
        return 'https://' + raw
    # Если с @username
    if raw.startswith('@'):
        return f'https://t.me/{raw[1:]}'
    # Во всех остальных случаях считаем это username
    return f'https://t.me/{raw}'

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # Determine the message object (supports command or callback)
    if update.callback_query:
        message = update.callback_query.message
    else:
        message = update.message
    user = update.effective_user
    # 1) Ensure user is subscribed to the required channel
    subscribed = False
    try:
        member = await context.bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user.id)
        if member.status in ('member', 'creator', 'administrator'):
            subscribed = True
    except Exception as e:
        logger.error(f"Subscription check failed or user not found: {e}")

    if not subscribed:
        await message.reply_text(
            "<b>✌️Привет!</b>\n\n"
            "<i>🔸Прежде чем двинемся дальше,\n"
            "подпишись на наш закрытый канал.</i>\n\n"
            "<b>Там вся движуха, инсайды и секретные фишки!</b>\n\n"
            "<b>☞https://t.me/+_C0oLC4YtHo2OGFi</b>",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("✅ Проверить подписку", callback_data='check_subscription')]]
            ),
            parse_mode='HTML'
        )
        return

    ref_by = None
    # Check for referrer in start parameters
    if update.message and update.message.text:
        text = update.message.text
        if text.startswith('/start'):
            parts = text.split(' ', 1)
            if len(parts) > 1:
                param = parts[1]
                if param.startswith('ref_'):
                    try:
                        ref_by = int(param[4:])
                    except ValueError:
                        ref_by = None
                else:
                    try:
                        ref_by = int(param)
                    except ValueError:
                        ref_by = None
    # Insert or update user with ref_by if not set
    cursor.execute("SELECT ref_by FROM users WHERE user_id = ?", (user.id,))
    existing = cursor.fetchone()
    if existing is None:
        cursor.execute("INSERT INTO users (user_id, username, first_name, last_name, ref_by) VALUES (?, ?, ?, ?, ?)",
                       (user.id, user.username, user.first_name, user.last_name, ref_by))
        conn.commit()
        # Schedule loyalty credit in 3 days if a referrer was set
        if ref_by is not None and ref_by != user.id:
            context.job_queue.run_once(
                credit_loyal_referral,
                when=3*24*60*60,
                chat_id=ref_by,
                data=user.id
            )
            await notify_simple_referral(context, ref_by)
    elif existing[0] is None and ref_by is not None and ref_by != user.id:
        cursor.execute("UPDATE users SET ref_by = ? WHERE user_id = ?", (ref_by, user.id))
        conn.commit()
        # Schedule loyalty credit in 3 days if a referrer was set
        if ref_by is not None and ref_by != user.id:
            context.job_queue.run_once(
                credit_loyal_referral,
                when=3*24*60*60,
                chat_id=ref_by,
                data=user.id
            )
            await notify_simple_referral(context, ref_by)
    
    # schedule reminder in 23 minutes
    context.job_queue.run_once(
        send_referral_reminder,
        when=23 * 60,
        chat_id=update.effective_chat.id
    )

    # Сразу после вставки/обновления пользователя
    cursor.execute("SELECT promo_code FROM users WHERE user_id = ?", (user.id,))
    if cursor.fetchone()[0] is None:
        new_code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        cursor.execute(
            "UPDATE users SET promo_code = ? WHERE user_id = ?",
            (new_code, user.id)
        )
    conn.commit()

    photo_caption = (
        '🥷 <b>AMB Promo — халява стала реальной!</b>\n\n'
        '🎁Купоны на Whoosh, Urent, Яндекс \n <b>от 100 до 1000 ₽</b>\n без вложений, просто за друзей!\n\n'
        '👉<i>Привёл друга → он остался в канале \n<b>→ 💖ЗАБРАЛ ПРОМО</b></i>\n\n'
        '🔄<i>Больше друзей — круче промокоды!</i>\n\n'
        '<b>Попробуй сам, это проще чем кажется</b>‼️\n\n'
        '⸻\n\n'
        '<b>👤Поддержка:</b> @amb_managers\n'
        '<b>💭Отзывы:</b> @otzv_amb\n'
        '<b>🎟️Купоны и товары:</b> @Kicksheringboss_bot'
    )
    user_id = user.id
    buttons = [
        [KeyboardButton("Задания")],
        [KeyboardButton("👤 Профиль"), KeyboardButton("ℹ️ Правила"), KeyboardButton("🛠 Поддержка")],
        [KeyboardButton("🔥Получить ПРОМО"), KeyboardButton("✅Ввести ПРОМО")]
    ]
    if user_id in ADMIN_IDS:
        buttons.append([KeyboardButton("Админ")])
    reply_keyboard = ReplyKeyboardMarkup(buttons, resize_keyboard=True)
    # Send welcome image with caption
    await message.reply_photo(
        photo=open(WELCOME_IMAGE_PATH, 'rb'),
        caption=photo_caption,
        parse_mode=ParseMode.HTML,
        reply_markup=reply_keyboard
    )
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="Прочитай наши правила",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("💡 Прочитать", callback_data='start_read_rules')]]
        )
    )
async def check_subscription_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user_id = query.from_user.id
    try:
        member = await context.bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        if member.status in ('member', 'creator', 'administrator'):
            await query.message.delete()
            # User is now subscribed; restart onboarding
            await start(update, context)
        else:
            await query.answer("Ты еще не подписан на канал.", show_alert=True)
        return
    except Exception as e:
        logger.error(f"Subscription re-check failed: {e}")
        await query.answer("Ошибка проверки подписки. Попробуй позже.", show_alert=True)
# --- ADMIN PANEL HANDLER ---
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # Clear any pending admin workflow stages
    context.user_data.pop('promo_stage', None)
    context.user_data.pop('content_stage', None)
    context.user_data.pop('broadcast_stage', None)
    context.user_data.pop('task_stage', None)
    # Удаляем сообщение, если оно есть
    try:
        await update.message.delete()
    except Exception:
        pass
    # Формируем новую клавиатуру для админа
    buttons = [
        [KeyboardButton("Контент"), KeyboardButton("Купоны"), KeyboardButton("Статистика")],
        [KeyboardButton("Рассылка"), KeyboardButton("Промо")],
        [KeyboardButton("Главная")]
    ]
    await update.message.reply_text(
        "👑 Панель администратора\n\nВыберите действие:",
        reply_markup=ReplyKeyboardMarkup(buttons, resize_keyboard=True)
    )

async def clear_chat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    # Только админ может чистить в группе или канале, в личке можно всегда
    if user_id not in ADMIN_IDS and update.effective_chat.type != ChatType.PRIVATE:
        await update.message.reply_text("Нет прав для очистки.")
        return

    # Получаем последние 50 сообщений в чате (только бот может удалять свои и свои же сообщения юзеров)
    async for msg in context.bot.get_chat_history(chat_id, limit=50):
        # Оставить приветственное сообщение (по фразе)
        if "AMB Promo — ты в игре!" in (msg.text or ""):
            continue
        try:
            await context.bot.delete_message(chat_id, msg.message_id)
        except Exception:
            pass

    await context.bot.send_message(chat_id, "Чат очищен. Приветствие осталось.")

# Состояние для ввода промокода
ENTER_CODE = 1

async def prompt_promo_code(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    # Убираем сообщение с кнопкой и просим ввести код
    # удаляем старое сообщение с кнопкой «Ввести промокод»
    await update.message.delete()
    # отправляем запрос и сохраняем его message_id, чтобы потом удалить
    prompt = await update.message.reply_text("🔑 Введите промокод, который вам дал друг:")
    context.user_data['promo_prompt_msg_id'] = prompt.message_id
    return ENTER_CODE

async def receive_promo_code(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    code = update.message.text.strip().upper()
    user_id = update.effective_user.id
    prompt_id = context.user_data.pop('promo_prompt_msg_id', None)
    if prompt_id:
        await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=prompt_id)
    # затем удаляем сообщение с введённым кодом
    await update.message.delete()

    # 1) Проверяем, что не свой собственный код
    cursor.execute("SELECT promo_code FROM users WHERE user_id = ?", (user_id,))
    my_code = cursor.fetchone()[0]
    if code == my_code:
        await context.bot.send_message(
            chat_id=user_id,
            text="❌ Нельзя вводить свой же промокод."
        )
        return ConversationHandler.END

    # 2) Ищем владельца кода
    cursor.execute("SELECT user_id FROM users WHERE promo_code = ?", (code,))
    row = cursor.fetchone()
    if not row:
        await context.bot.send_message(user_id, "❌ Промокод не найден. Попробуйте ещё раз.")
        return ConversationHandler.END
    owner_id = row[0]

    # 3) Проверяем, что реферал ещё не привязан
    cursor.execute("SELECT ref_by FROM users WHERE user_id = ?", (user_id,))
    if cursor.fetchone()[0] is not None:
        await context.bot.send_message(user_id, "⚠️ Вы уже привязаны к рефереру.")
        return ConversationHandler.END

    # 4) Сохраняем реферера и увеличиваем счётчик
    cursor.execute("UPDATE users SET ref_by = ? WHERE user_id = ?", (owner_id, user_id))
    cursor.execute("UPDATE users SET referrals_count = referrals_count + 1 WHERE user_id = ?", (owner_id,))
    conn.commit()

    # Schedule loyalty credit in 3 days
    context.job_queue.run_once(
        credit_loyal_referral,
        when=3*24*60*60,
        chat_id=owner_id,
        data=user_id
    )
    # 5а) Отправляем активацию + кнопку «Забрать»
    response_msg = await context.bot.send_message(
        chat_id=user_id,
        text=(
            "✅NICE Ваш промо <b>АКТИВИРОВАН</b>\n\n"
            "🎁<b>ВАМ ДОСТУПЕН ПОДАРОК</b>"
        ),
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("👉ЗАБРАТЬ👈", callback_data='get_gift')
        ]])
    )
    # — владельцу кода
    await context.bot.send_message(
        chat_id=owner_id,
        text="✅<b>У тебя +1 новый реферал‼️</b>\n🎉Проверь профиль",
        parse_mode=ParseMode.HTML
    )
    return ConversationHandler.END

# --- CONTENT COMMAND HANDLER ---
async def content_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        return
    await update.message.delete()
    buttons = [
        [KeyboardButton("📥 Добавить мем"), KeyboardButton("🗑 Удалить мем")],
        [KeyboardButton("✍️ Добавить текст"), KeyboardButton("🧾 Список текстов")],
        [KeyboardButton("📋 Список чатов")],
        [KeyboardButton("➕ Добавить чат"), KeyboardButton("🗑 Удалить чат")],
        [KeyboardButton("🔙 Назад")]
    ]
    reply_keyboard = ReplyKeyboardMarkup(buttons, resize_keyboard=True)
    await update.message.reply_text(
        "🧠 Контент-задания\nВыбери, с чем хочешь работать:",
        reply_markup=reply_keyboard
    )


# Handler for reply-keyboard "📥 Добавить мем"
async def content_add_meme_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        return
    # Удаляем сообщение с кнопкой, сохраняем картинку и сразу добавляем в БД
    await update.message.delete()
    context.user_data.pop('content_stage', None)
    await update.message.reply_text("📥 Пришлите мем (JPG/PNG):")
    context.user_data['content_stage'] = CONTENT_STAGE_ADD_MEME

async def content_delete_meme_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        return
    await update.message.delete()
    # List existing memes
    cursor.execute("SELECT id, text FROM meme_templates")
    memes = cursor.fetchall()
    if not memes:
        await update.message.reply_text("Нет мемов для удаления.", reply_markup=back_inline_markup)
        return
    msg_lines = ["🗑 Список мемов (ID — подпись):"]
    for mid, txt in memes:
        snippet = txt if len(txt) <= 30 else txt[:30] + "..."
        msg_lines.append(f"{mid} — {snippet}")
    msg_lines.append("\nПришлите ID мема для удаления.")
    await update.message.reply_text("\n".join(msg_lines))
    context.user_data['content_stage'] = CONTENT_STAGE_DELETE_MEME

# Handler for reply-keyboard "📋 Список чатов"
async def content_list_chats_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        return
    await update.message.delete()
    cursor.execute("SELECT chat_username FROM allowed_chats ORDER BY RANDOM()")
    chats = [row[0] for row in cursor.fetchall()]
    if not chats:
        await update.message.reply_text("Список чатов пуст.", reply_markup=back_inline_markup)
        return
    msg = "📋 Список чатов:\n" + "\n".join(f"{i+1}. {chat}" for i, chat in enumerate(chats))
    await update.message.reply_text(msg, reply_markup=back_inline_markup)

# Handler for reply-keyboard "➕ Добавить чат"
async def content_add_chat_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        return
    await update.message.delete()
    context.user_data['content_stage'] = CONTENT_STAGE_ADD_CHAT
    await update.message.reply_text("➕ Введите @username, t.me/... или полную ссылку на чат:")

# Handler for reply-keyboard "🗑 Удалить чат"
async def content_delete_chat_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        return
    await update.message.delete()
    # Fetch chats in a consistent, sorted order
    cursor.execute("SELECT chat_username FROM allowed_chats ORDER BY chat_username")
    chats = [row[0] for row in cursor.fetchall()]
    # Store the ordered list for deletion reference
    context.user_data['delete_chats_list'] = chats
    if not chats:
        await update.message.reply_text("Нет чатов для удаления.", reply_markup=back_inline_markup)
        return
    msg = "🗑 Список чатов:\n" + "\n".join(f"{i+1}. {chat}" for i, chat in enumerate(chats)) + "\n\nПришлите номер для удаления."
    await update.message.reply_text(msg)
    context.user_data['content_stage'] = CONTENT_STAGE_DELETE_CHAT

# --- PROMO OFFERS COMMAND HANDLER ---
async def promo_panel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        return
    await update.message.delete()
    buttons = [
        [KeyboardButton("📥 Добавить оффер"), KeyboardButton("🗑 Удалить оффер")],
        [KeyboardButton("📋 Список офферов")],
        [KeyboardButton("🔙 Назад")]
    ]
    reply_keyboard = ReplyKeyboardMarkup(buttons, resize_keyboard=True)
    await update.message.reply_text(
        "💎 Promo-оферы\nВыберите действие:",
        reply_markup=reply_keyboard
    )

# Handler for reply-keyboard "📥 Добавить оффер"
async def promo_add_offer_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        return
    await update.message.delete()
    context.user_data['promo_stage'] = PROMO_STAGE_ADD
    await update.message.reply_text("📥 Введите оффер в формате: Название — стоимость (целое число)")

# Handler for reply-keyboard "🗑 Удалить оффер"
async def promo_delete_offer_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        return
    await update.message.delete()
    cursor.execute("SELECT offer_id, title, cost FROM promo_offers")
    rows = cursor.fetchall()
    if not rows:
        await update.message.reply_text("Нет офферов для удаления.", reply_markup=back_inline_markup)
        return
    msg_lines = ["🗑 Список офферов (ID — Название — Стоимость):"]
    for oid, title, cost in rows:
        msg_lines.append(f"{oid} — {title} — {cost}")
    msg_lines.append("\nПришлите ID оффера для удаления.")
    await update.message.reply_text("\n".join(msg_lines))
    context.user_data['promo_stage'] = PROMO_STAGE_DELETE

# Handler for reply-keyboard "📋 Список офферов"
async def promo_list_offers_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        return
    await update.message.delete()
    cursor.execute("SELECT offer_id, title, cost FROM promo_offers")
    rows = cursor.fetchall()
    if not rows:
        await update.message.reply_text("Список офферов пуст.", reply_markup=back_inline_markup)
        return
    lines = ["📋 Список офферов (ID — Название — Стоимость):"]
    for oid, title, cost in rows:
        lines.append(f"{oid} — {title} — {cost}")
    await update.message.reply_text("\n".join(lines), reply_markup=back_inline_markup)


# --- USER PROMO FLOW ---
async def promo_user_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # Handle reply-button "Получить промо"
    msg = update.message
    user_id = msg.from_user.id
    await msg.delete()
    await msg.reply_text(
        "За друзей — промокоды.\n🎁Проверь, хватает ли на подарок",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("😚Проверить", callback_data='promo_choose')]])
    )

async def promo_choose_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    # send and save intro text
    intro_msg = await query.message.reply_text(
        "💭<b>ОП ОП ОП</b>\n\n"
        "💥<i>Ты уже пришёл за подарками!</i>\n\n"
        "🎁<b>Вот что можно получить:</b>\n<i>Цена указана справа от названия</i>\n\n"
        "💖 <b>1 преданный реферал = 1💖</b>\n\n"
        "💕 <b>Преданный реферал</b> — тот, кто остался в боте 3 дня после перехода по твоей ссылке.",
        parse_mode=ParseMode.HTML
    )
    context.user_data['promo_intro_msg_id'] = intro_msg.message_id
    # delete original prompt
    await query.message.delete()
    cursor.execute("SELECT offer_id, title, cost FROM promo_offers")
    rows = cursor.fetchall()
    if not rows:
        await query.message.reply_text("Пока нет доступных промо, зайди позже.", reply_markup=back_inline_markup)
        return
    keyboard = [[InlineKeyboardButton(f"{title} за {cost}💖", callback_data=f'promo_offer|{oid}')] for oid, title, cost in rows]
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data='promo_back')])
    await query.message.reply_text("🛒<b>ВЫБЕРИ ТОВАР</b>", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.HTML)

async def promo_back_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    # delete intro message if exists
    intro_id = context.user_data.pop('promo_intro_msg_id', None)
    if intro_id:
        await context.bot.delete_message(chat_id=query.message.chat_id, message_id=intro_id)
    # delete the current list message
    await query.message.delete()
    # return to main keyboard

async def promo_offer_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    _, oid = query.data.split('|', 1)
    cursor.execute("SELECT title, cost FROM promo_offers WHERE offer_id = ?", (oid,))
    row = cursor.fetchone()
    if not row:
        await query.message.reply_text("Ошибка: оффер не найден.", reply_markup=back_inline_markup)
        return
    title, cost = row
    user_id = query.from_user.id
    # Count only those referrals who stayed in the channel ≥3 days
    cursor.execute("SELECT loyal_referrals FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    total_loyal = row[0] if row else 0

    cursor.execute("SELECT used_loyal FROM users WHERE user_id = ?", (user_id,))
    used_loyal = cursor.fetchone()[0] or 0
    available = total_loyal - used_loyal
    if available < cost:
        # remove the promo list and intro messages
        await query.message.delete()
        intro_id = context.user_data.pop('promo_intro_msg_id', None)
        if intro_id:
            await context.bot.delete_message(
                chat_id=query.message.chat_id, message_id=intro_id
            )
        # Notify user with softer message and a back button
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=(
                "🙈<i>Упс, похоже тебе пока не хватает преданных рефералов</i>\n\n"
                f"➖<b>У тебя сейчас {available}/{cost}</b>\n\n"
                "🗣️<b>Попробуй пригласить ещё</b>"
            ),
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("🔙 Назад", callback_data='promo_back')]]
            )
        )
        return
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("Да", callback_data=f'promo_confirm|{oid}')],
        [InlineKeyboardButton("Нет", callback_data='promo_back')]
    ])
    await query.message.delete()
    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text=f"Хочешь получить «{title}» за {cost} преданных?",
        reply_markup=keyboard
    )

async def promo_confirm_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    _, oid = query.data.split('|', 1)
    cursor.execute("SELECT title, cost FROM promo_offers WHERE offer_id = ?", (oid,))
    row = cursor.fetchone()
    if not row:
        await query.message.reply_text("Ошибка: оффер не найден.", reply_markup=back_inline_markup)
        return
    title, cost = row
    user_id = query.from_user.id
    # Recount available
    cursor.execute("SELECT loyal_referrals FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    total_loyal = row[0] if row else 0
        
    cursor.execute("SELECT used_loyal FROM users WHERE user_id = ?", (user_id,))
    used_loyal = cursor.fetchone()[0] or 0
    available = total_loyal - used_loyal
    if available < cost:
        await query.answer("Недостаточно преданных рефералов.", show_alert=True)
        return
    # Deduct the cost from the user's loyal referrals
    cursor.execute(
        "UPDATE users SET used_loyal = used_loyal + ? WHERE user_id = ?",
        (cost, user_id)
    )
    conn.commit()
    # Create promo task
    now = datetime.now()
    cursor.execute(
        "INSERT INTO tasks (user_id, task_type, task_description, created_at) VALUES (?, 'promo', ?, ?)",
        (user_id, f"offer:{oid}", now)
    )
    task_id = cursor.lastrowid
    conn.commit()

    # Notify all admins of new promo request
    for admin_id in ADMIN_IDS:
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Одобрить", callback_data=f'approve_task|{task_id}')],
            [InlineKeyboardButton("❌ Отклонить", callback_data=f'decline_task|{task_id}')]
        ])
        await context.bot.send_message(
            chat_id=admin_id,
            text=(
                f"📥 <b>Новая заявка на промо</b>\n"
                f"От @{update.effective_user.username or user_id}\n"
                f"Оффер: {title} за {cost}💖\n"
                f"ID задачи: {task_id}"
            ),
            parse_mode=ParseMode.HTML,
            reply_markup=keyboard
        )
    await query.message.delete()
    await context.bot.send_message(
        chat_id=user_id,
        text="Заявка на промо отправлена на проверку. Жди ответа в профиле."
    )

# Handler for reply-keyboard "✍️ Добавить текст"
async def content_add_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        return
    try:
        await update.message.delete()
    except Exception:
        pass
    context.user_data['content_stage'] = CONTENT_STAGE_ADD_TEXT
    await update.message.reply_text("✍️ Введите текст для нового задания:")

async def content_list_texts_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        return
    await update.message.delete()
    cursor.execute("SELECT id, text FROM text_templates")
    rows = cursor.fetchall()
    if not rows:
        await update.message.reply_text("Список текстов пуст.", reply_markup=back_inline_markup)
        return
    msg_lines = ["🧾 Список текстов (ID — начало текста):"]
    for tid, txt in rows:
        snippet = txt if len(txt) <= 30 else txt[:30] + "..."
        msg_lines.append(f"{tid} — {snippet}")
    msg_lines.append("\nПришлите ID текста для удаления.")
    await update.message.reply_text("\n".join(msg_lines))
    context.user_data['content_stage'] = CONTENT_STAGE_LIST_TEXTS

# Handler for reply-keyboard "Проверить задания"
async def check_tasks_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        return
    await update.message.delete()
    # Fetch next pending task with screenshot, including created_at
    cursor.execute(
        "SELECT task_id, user_id, screenshot_path, created_at FROM tasks "
        "WHERE status='pending' AND screenshot_path IS NOT NULL "
        "ORDER BY created_at ASC LIMIT 1"
    )
    row = cursor.fetchone()
    if not row:
        await context.bot.send_message(
            chat_id=user_id,
            text="Нет новых заявок на проверку.",
            reply_markup=ReplyKeyboardMarkup([[KeyboardButton("Главная")]], resize_keyboard=True)
        )
        return
    task_id, task_user_id, screenshot_path, created_at = row
    # Get username
    cursor.execute("SELECT username FROM users WHERE user_id = ?", (task_user_id,))
    uname = cursor.fetchone()[0] or str(task_user_id)
    # Send screenshot
    if os.path.exists(screenshot_path):
        photo_message = await context.bot.send_photo(chat_id=user_id, photo=open(screenshot_path, 'rb'))
        # Store photo message id for later deletion
        context.user_data['last_task_photo_msg_id'] = photo_message.message_id
        context.user_data['last_task_photo_chat_id'] = user_id
    text = (
        f"Новая заявка от @{uname}\n"
        f"ID: {task_id}\n"
        f"Дата подачи: {created_at}"
    )
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Одобрить", callback_data=f'approve_task|{task_id}')],
        [InlineKeyboardButton("❌ Отклонить", callback_data=f'decline_task|{task_id}')]
    ])
    await context.bot.send_message(
        chat_id=user_id,
        text=text,
        reply_markup=keyboard
    )

async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    cursor.execute(
        "SELECT username, first_name, last_name, promo_code FROM users WHERE user_id = ?",
        (user.id,)
    )
    username, first_name, last_name, promo_code = cursor.fetchone()
    # Count referrals
    cursor.execute("SELECT COUNT(*) FROM users WHERE ref_by = ?", (user.id,))
    referrals_count = cursor.fetchone()[0]
    # Count completed tasks
    cursor.execute("SELECT COUNT(*) FROM tasks WHERE user_id = ? AND status = 'approved'", (user.id,))
    tasks_count = cursor.fetchone()[0]
    # Count tasks pending approval
    cursor.execute("SELECT COUNT(*) FROM tasks WHERE user_id = ? AND status = 'pending'", (user.id,))
    pending_count = cursor.fetchone()[0]
        # Получаем кол-во преданных рефералов из БД
    cursor.execute("SELECT loyal_referrals FROM users WHERE user_id = ?", (user.id,))
    row = cursor.fetchone()
    total_loyal = row[0] if row else 0

    # Получаем сколько уже потрачено
    cursor.execute("SELECT used_loyal FROM users WHERE user_id = ?", (user.id,))
    used_loyal = cursor.fetchone()[0] or 0

    # Считаем сколько доступно
    available = total_loyal - used_loyal
    if available < 0:
        available = 0
    # Build formatted profile text (HTML mode)
    profile_text = (
        "<b>💼ПРОФИЛЬ:</b>\n\n"
        f"<b>👤 User:</b> @{username or 'нет'}\n"
        f"<b>🆔 ID:</b> {user.id}\n\n"
        f"<b>💰 Твои рефералы:</b> {referrals_count}\n"
        f"<b>💕ПРЕДАННЫЕ РЕФЕРАЛЫ:</b> {available}\n"
        f"<b>💔 Потрачено 💖:</b> {used_loyal}\n\n"
        f"<b>🔥 Заданий выполнено:</b> {tasks_count}\n"
        f"<b>⏳ Заданий на проверке:</b> {pending_count}\n\n"
        f"<b>🔑 Ваш промокод:</b> <code>{promo_code}</code>\n\n"
        "<b>🔗 Твоя реф-ссылка:</b>\n"
        f"<a href=\"https://t.me/AMB_Promo_bot?start=ref_{user.id}\">https://t.me/AMB_Promo_bot?start=ref_{user.id}</a>"
    )
    # Send or edit with HTML parse mode
    if update.callback_query:
        await update.callback_query.edit_message_text(profile_text, parse_mode=ParseMode.HTML)
    else:
        # Remove user's message to clean up chat
        await update.message.delete()
        await update.message.reply_text(
            profile_text,
            parse_mode=ParseMode.HTML,
            reply_markup=back_inline_markup
        )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    # --- Broadcast Cancel Handler (must be before any 'broadcast_all' or 'broadcast_user' etc.) ---
    if query.data == 'bc_cancel':
        reset_broadcast_state(context)
        await query.message.delete()
        await query.message.reply_text("Рассылка отменена.", reply_markup=back_inline_markup)
        return

    # Approve/Decline task callbacks
    if query.data.startswith('approve_task'):
        _, task_id = query.data.split('|', 1)
        # fetch task details
        cursor.execute("SELECT user_id, task_type FROM tasks WHERE task_id = ?", (task_id,))
        row = cursor.fetchone()
        user_id, task_type = row
        if task_type == 'promo':
            # prompt admin for coupon code
            context.user_data['task_stage'] = 'await_promo_code'
            context.user_data['task_id'] = task_id
            context.user_data['task_user_id'] = user_id
            await query.message.edit_text(
                "Введите код купона для промо:",
                reply_markup=back_inline_markup
            )
            return
        # generic approval for other tasks
        cursor.execute("UPDATE tasks SET status='approved' WHERE task_id = ?", (task_id,))
        cursor.execute(
            "UPDATE users SET pending_tasks = pending_tasks - 1, completed_tasks = completed_tasks + 1 WHERE user_id = ?",
            (user_id,)
        )
        conn.commit()
        await context.bot.send_message(
            chat_id=user_id,
            text=(
                "😈*ВААЙ КРАСАУЧИК\n"
                "Задание одобрил сам АДМИН!*\n\n"
                "📈_Еще *ЧУТ ЧУТ* и катася бесплатно будешь!!!_\n\n"
                "♦️*Проверь в профиле сколько рефералов пришло*♦️"
            ),
            parse_mode=ParseMode.MARKDOWN
        )
        # delete admin inline and any photo
        photo_msg_id = context.user_data.pop('last_task_photo_msg_id', None)
        photo_chat_id = context.user_data.pop('last_task_photo_chat_id', None)
        if photo_msg_id and photo_chat_id:
            await context.bot.delete_message(chat_id=photo_chat_id, message_id=photo_msg_id)
        await query.message.delete()
        return

    elif query.data.startswith('decline_task'):
        _, task_id = query.data.split('|', 1)
        # fetch the task's user
        cursor.execute("SELECT user_id FROM tasks WHERE task_id = ?", (task_id,))
        user_id = cursor.fetchone()[0]
        # update task status
        cursor.execute("UPDATE tasks SET status='declined' WHERE task_id = ?", (task_id,))
        # update user counters
        cursor.execute(
            "UPDATE users SET pending_tasks = pending_tasks - 1 WHERE user_id = ?",
            (user_id,)
        )
        conn.commit()
        # notify the user
        await context.bot.send_message(
            chat_id=user_id,
            text=(
                "*😕АЙ БРАТ ОБИЖАЕШЬ*\n\n"
                "➖_Задание не одобрил админ\nВозможно, ты не выполнил условия или не приложил скриншот._\n\n"
                "☑️*Попробуй еще раз!*"
            ),
            parse_mode=ParseMode.MARKDOWN
        )
        # delete admin's inline message and any photo
        photo_msg_id = context.user_data.pop('last_task_photo_msg_id', None)
        photo_chat_id = context.user_data.pop('last_task_photo_chat_id', None)
        if photo_msg_id and photo_chat_id:
            await context.bot.delete_message(chat_id=photo_chat_id, message_id=photo_msg_id)
        await query.message.delete()
        return

    if query.data == 'start_read_rules':
        await query.message.delete()
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=rules_text,
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("✅ Прочитал", callback_data='start_accept_rules')]]
            )
        )
        return
    if query.data == 'start_accept_rules':
        await query.message.delete()
        # show main reply keyboard instead of inline participate
        await send_main_reply_keyboard(update, context)
        return

    if query.data == 'participate':
        await query.message.delete()
        await show_participate_menu(update, context)
    elif query.data == 'task_meme':
        await handle_task_meme(update, context)
    elif query.data == 'task_text':
        await handle_task_text(update, context)
    elif query.data == 'task_repost':
        await handle_task_repost(update, context)
    elif query.data == 'task_back':
        reset_broadcast_state(context)
        await handle_task_back(update, context)
    elif query.data == 'task_other_text':
        await handle_task_other_text(update, context)
    elif query.data == 'task_other_meme':
        await handle_task_other_meme(update, context)
        return
    elif query.data == 'task_done':
        await handle_task_done(update, context)
    elif query.data == 'profile':
        await query.message.delete()
        cursor.execute("SELECT username, first_name, last_name FROM users WHERE user_id = ?", (user_id,))
        user_row = cursor.fetchone()
        if user_row:
            username, first_name, last_name = user_row
            cursor.execute("SELECT COUNT(*) FROM users WHERE ref_by = ?", (user_id,))
            referrals = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM tasks WHERE user_id = ?", (user_id,))
            tasks_count = cursor.fetchone()[0]
            profile_text = (
                f"👤 Твой профиль AMB PromoDealer\n\n"
                f"📎 Telegram: @{username if username else 'нет'}\n"
                f"🆔 ID: {user_id}\n"
                f"👥 Рефералов: {referrals}\n"
                f"🧩 Выполнено заданий: {tasks_count}\n\n"
                f"🔗 Ваша реферальная ссылка:\n"
                f"t.me/AMBpromo_bot?start=ref_{user_id}"
            )
        else:
            profile_text = "Профиль не найден."
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=profile_text,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data='task_back')]])
        )
    elif query.data == 'rules':
        await query.message.delete()
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=rules_text,
            parse_mode=ParseMode.HTML,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data='task_back')]])
        )
    elif query.data == 'support':
        support_text = "По вопросам: @amb_support"
        await query.message.delete()
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=support_text,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data='task_back')]])
        )
    elif query.data == 'admin_broadcast':
        await query.message.delete()
        keyboard = [
            [
                InlineKeyboardButton("Всем", callback_data='broadcast_all'),
                InlineKeyboardButton("Пользователю", callback_data='broadcast_user')
            ],
            [InlineKeyboardButton("🔙 Назад", callback_data='task_back')],
            [InlineKeyboardButton("❌ Отмена", callback_data='bc_cancel')]
        ]
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text="Выберите режим рассылки:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    elif query.data == 'broadcast_all':
        await query.message.delete()
        context.user_data['broadcast_stage'] = BROADCAST_STAGE_TEXT
        context.user_data['broadcast_text'] = None
        context.user_data['broadcast_photo'] = None
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text="Пришлите текст для рассылки *всем* пользователям.",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data='task_back')]])
        )
    elif query.data == 'broadcast_user':
        await query.message.delete()
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text="Пришлите сообщение в формате `@username текст` для одного пользователя.\nПоддерживается Markdown, эмодзи и опциональное фото.",
            parse_mode='Markdown'
        )
        context.user_data['broadcast_mode'] = 'user'

    elif query.data == 'bc_attach_photo':
        await query.message.delete()
        context.user_data['broadcast_stage'] = BROADCAST_STAGE_PHOTO
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text="Прикрепите фото для рассылки.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data='task_back')]])
        )
    elif query.data == 'bc_send_confirm':
        await query.message.delete()
        context.user_data['broadcast_stage'] = BROADCAST_STAGE_CONFIRM
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text="Вы уверены, что хотите отправить рассылку *всем*?",
            parse_mode=ParseMode.MARKDOWN_V2,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Да", callback_data='bc_execute')],
                [InlineKeyboardButton("🔙 Назад", callback_data='task_back')]
            ])
        )
    elif query.data == 'bc_execute':
        await query.message.delete()
        text = context.user_data.get('broadcast_text', '')
        photo_path = context.user_data.get('broadcast_photo')
        sent, errors = 0, 0
        cursor.execute("SELECT user_id FROM users")
        for (uid,) in cursor.fetchall():
            try:
                if photo_path and os.path.exists(photo_path):
                    await context.bot.send_photo(chat_id=uid, photo=open(photo_path, 'rb'), caption=text, parse_mode=ParseMode.HTML)
                else:
                    await context.bot.send_message(chat_id=uid, text=text, parse_mode=ParseMode.HTML)
                sent += 1
            except:
                errors += 1
        context.user_data['broadcast_stage'] = None
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=f"Рассылка завершена: {sent} успешно, {errors} ошибок."
        )
    elif query.data == 'get_gift':
        # подтверждаем нажатие и удаляем предыдущее сообщение с кнопкой
        await query.answer()
        await query.message.delete()

        # 1) Генерируем или берём статический подарок-код
        gift_code = "QODMSH"  # можно динамически вытаскивать из БД

        # 2) Отправляем детали подарка
        await context.bot.send_message(
            chat_id=query.from_user.id,
            text=(
                "🎁<b>ТВОЙ ПОДАРОК</b>\n\n"
                "👉<i>Промокод на сервис ЮРЕНТ</i>👈\n\n"
                f"🎫<b>ПРОМО:</b> <code>{gift_code}</code>\n"
                "(⬆️нажми на код чтобы скопировать⬆️)\n\n"
                "<i>Дает</i> <b>СКИДКУ В 50%</b> <i>на первые 2 поездки</i>"
            ),
            parse_mode=ParseMode.HTML
        )

# --- PARTICIPATE TASKS MENU AND HANDLERS ---
async def show_participate_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # Handle both callback_query and direct message triggers
    if update.callback_query:
        query = update.callback_query
        await query.answer()
        target = query.message
        keyboard = [
            [InlineKeyboardButton("🧠 Мем", callback_data='task_meme')],
            [InlineKeyboardButton("🗣 Текст", callback_data='task_text')],
            [InlineKeyboardButton("🔙 Назад", callback_data='task_back')],
        ]
        await target.reply_text(
            "Выберите тип задания:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    else:
        # Remove user's "Задания" message
        await update.message.delete()
        # (Removed deletion of previous main-screen message to keep reply keyboard visible)
        # target = update.message  # we can reuse for reply (though message is deleted)
        keyboard = [
            [InlineKeyboardButton("🧠 Мем", callback_data='task_meme')],
            [InlineKeyboardButton("🗣 Текст", callback_data='task_text')],
            [InlineKeyboardButton("🔙 Назад", callback_data='task_back')],
        ]
        # Reply to the chat, not to the deleted message object
        chat_id = update.effective_chat.id
        await context.bot.send_message(
            chat_id=chat_id,
            text="Выберите тип задания:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

async def handle_task_meme(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    # Удаляем меню выбора
    try:
        await query.message.delete()
    except BadRequest:
        pass

    # 1) Берём случайный шаблон мема (id, путь к файлу). Текст игнорируем.
    cursor.execute(
        "SELECT id, file_path FROM meme_templates ORDER BY RANDOM() LIMIT 1"
    )
    row = cursor.fetchone()
    if not row:
        await query.message.reply_text("Шаблонов мемов пока нет.")
        return
    tpl_id, file_path = row

    # Формируем “плашку” с личным промокодом
    cursor.execute("SELECT promo_code FROM users WHERE user_id = ?", (query.from_user.id,))
    promo_code = cursor.fetchone()[0]
    panel = (
        "🔎 Ищи в поиске @AMB_Promo_bot и\n"
        f"‼️ Вводи этот <b>ПРОМО:</b> <code>{promo_code}</code>\n"
        "🎁 И получи свой <b>ПОДАРОК</b>"
    )

    # 2) Регистрируем задачу в БД
    now = datetime.now()
    cursor.execute(
        "INSERT INTO tasks (user_id, task_type, task_description, created_at) "
        "VALUES (?, 'meme', ?, ?)",
        (query.from_user.id, panel, now)
    )
    conn.commit()

    # 3) Увеличиваем счётчик ожидающих заданий
    cursor.execute(
        "UPDATE users SET pending_tasks = pending_tasks + 1 WHERE user_id = ?",
        (query.from_user.id,)
    )
    conn.commit()

    # 4) Отправляем сам мем
    if os.path.exists(file_path):
        photo_msg = await query.message.reply_photo(
            photo=open(file_path, 'rb'),
            caption=panel,
            parse_mode=ParseMode.HTML
        )
        context.user_data['last_meme_msg_id'] = photo_msg.message_id
    else:
        await query.message.reply_text("Файл мема не найден.")
        return

    # 5) Берём все чаты и выбираем не более 5 случайных
    cursor.execute("SELECT chat_username FROM allowed_chats")
    all_chats = [r[0] for r in cursor.fetchall()]
    # случайная выборка до 5
    chats = random.sample(all_chats, k=min(5, len(all_chats)))

    # 6) Строим инлайн-кнопки со ссылками (нормализуем URL)
    buttons = [
        [InlineKeyboardButton(text=chat, url=make_chat_url(chat))]
        for chat in chats
    ]
    # 7) Добавляем кнопки управления заданием
    buttons.append([
        InlineKeyboardButton("✅ Я выполнил", callback_data='task_done'),
        InlineKeyboardButton("🔙 Назад", callback_data='task_back'),
        InlineKeyboardButton("🔄 Другой", callback_data='task_other_meme')
    ])

    # 8) Отправляем сообщение с кнопками
    list_msg = await context.bot.send_message(
        chat_id=query.message.chat.id,
        text="Список чатов, куда можешь отправить этот мем:",
        reply_markup=InlineKeyboardMarkup(buttons)
    )
    context.user_data['last_task_msg_id'] = list_msg.message_id

async def handle_task_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    # удаляем меню выбора
    try:
        await query.message.delete()
    except BadRequest:
        pass

    # 1) Берём случайный шаблон текста из text_templates
    cursor.execute("SELECT id, text FROM text_templates ORDER BY RANDOM() LIMIT 1")
    row = cursor.fetchone()
    if not row:
        await query.message.reply_text("Шаблонов текста пока нет.")
        return
    tpl_id, txt = row

    # 2) Регистрируем задачу в БД
    now = datetime.now()
    cursor.execute(
        "INSERT INTO tasks (user_id, task_type, task_description, created_at) "
        "VALUES (?, ?, ?, ?)",
        (query.from_user.id, 'text', txt, now)
    )
    conn.commit()

    # 3) Увеличиваем счётчик ожидающих заданий у пользователя
    cursor.execute(
        "UPDATE users SET pending_tasks = pending_tasks + 1 WHERE user_id = ?",
        (query.from_user.id,)
    )
    conn.commit()

    # 4) Получаем постоянный промокод пользователя
    cursor.execute("SELECT promo_code FROM users WHERE user_id = ?", (query.from_user.id,))
    promo_code = cursor.fetchone()[0]

    # 5) Формируем новый текст задания
    combined = (
        f"{txt}\n\n"  # шаблон администратора
        "🔎 Ищи в поиске @AMB_Promo_bot и\n"
        f"‼️ Вводи этот <b>ПРОМО:</b> <code>{promo_code}</code>\n"
        "🎁 И получи свой <b>ПОДАРОК</b>"
    )
    content_msg = await query.message.reply_text(
        combined,
        parse_mode=ParseMode.HTML
    )
    context.user_data['last_task_content_msg_id'] = content_msg.message_id

    # 6) Получаем все чаты, выбираем случайно не более 5
    cursor.execute("SELECT chat_username FROM allowed_chats")
    all_chats = [r[0] for r in cursor.fetchall()]
    chats = random.sample(all_chats, k=min(5, len(all_chats)))

    # 7) Строим инлайн-кнопки со ссылками (нормализуем URL)
    buttons = [
        [InlineKeyboardButton(text=chat, url=make_chat_url(chat))]
        for chat in chats
    ]
    # + кнопки управления заданием
    buttons.append([
        InlineKeyboardButton("✅ Я выполнил", callback_data='task_done'),
        InlineKeyboardButton("🔙 Назад", callback_data='task_back'),
        InlineKeyboardButton("🔄 Другой", callback_data='task_other_text')
    ])

    # 8) Отправляем сообщение с кнопками
    list_msg = await context.bot.send_message(
        chat_id=query.message.chat.id,
        text="Отправь ⬆️⬆️⬆️ текст в любой из чатов ниже:",
        reply_markup=InlineKeyboardMarkup(buttons)
    )
    context.user_data['last_task_msg_id'] = list_msg.message_id
    
async def handle_task_other_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    # Удаляем предыдущие сообщения с заданием
    chat_id = query.message.chat.id
    for key in ('last_task_content_msg_id', 'last_task_msg_id'):
        msg_id = context.user_data.pop(key, None)
        if msg_id:
            try:
                await context.bot.delete_message(chat_id=chat_id, message_id=msg_id)
            except:
                pass
    # Шлём новое текстовое задание
    await handle_task_text(update, context)
    
async def handle_task_other_meme(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat.id

    # 1) Удаляем предыдущие сообщения с мемом и кнопками
    for key in ('last_meme_msg_id', 'last_task_msg_id'):
        msg_id = context.user_data.pop(key, None)
        if msg_id:
            try:
                await context.bot.delete_message(chat_id=chat_id, message_id=msg_id)
            except:
                pass

    # 2) Берём случайный шаблон мема (id и путь)
    cursor.execute(
        "SELECT id, file_path FROM meme_templates ORDER BY RANDOM() LIMIT 1"
    )
    row = cursor.fetchone()
    if not row:
        await query.message.reply_text("Шаблонов мемов пока нет.")
        return
    tpl_id, file_path = row

    # 3) Формируем “плашку” с личным промокодом и регистрируем таск
    cursor.execute("SELECT promo_code FROM users WHERE user_id = ?", (query.from_user.id,))
    promo_code = cursor.fetchone()[0]
    panel = (
        "🔎 Ищи в поиске @AMB_Promo_bot и\n"
        f"‼️ Вводи этот <b>ПРОМО:</b> <code>{promo_code}</code>\n"
        "🎁 И получи свой <b>ПОДАРОК</b>"
    )
    now = datetime.now()
    cursor.execute(
        "INSERT INTO tasks (user_id, task_type, task_description, created_at) "
        "VALUES (?, 'meme', ?, ?)",
        (query.from_user.id, panel, now)
    )
    cursor.execute(
        "UPDATE users SET pending_tasks = pending_tasks + 1 WHERE user_id = ?",
        (query.from_user.id,)
    )
    conn.commit()

    # 4) Отправляем мем с нашей панелью
    if os.path.exists(file_path):
        photo_msg = await query.message.reply_photo(
            photo=open(file_path, 'rb'),
            caption=panel,
            parse_mode=ParseMode.HTML
        )
        context.user_data['last_meme_msg_id'] = photo_msg.message_id
    else:
        await query.message.reply_text("Файл мема не найден.")
        return

    # 5) Берём все чаты и выбираем не более 5 случайных
    cursor.execute("SELECT chat_username FROM allowed_chats")
    all_chats = [r[0] for r in cursor.fetchall()]
    chats = random.sample(all_chats, k=min(5, len(all_chats)))

    # 6) Строим и отправляем инлайн-кнопки со ссылками
    buttons = [
        [InlineKeyboardButton(text=chat, url=make_chat_url(chat))]
        for chat in chats
    ]
        # + кнопки управления заданием с возможностью отмены
    buttons.append([
        InlineKeyboardButton("✅ Я выполнил", callback_data='task_done'),
        InlineKeyboardButton("🔙 Назад", callback_data='task_back'),
        InlineKeyboardButton("🔄 Другой", callback_data='task_other_meme')
    ])
    list_msg = await context.bot.send_message(
        chat_id=chat_id,
        text="Ниже список чатов, куда можешь отправить ⬆️ этот ⬆️ мем:",
        reply_markup=InlineKeyboardMarkup(buttons)
    )
    context.user_data['last_task_msg_id'] = list_msg.message_id
    
async def handle_task_repost(update, context):
    query = update.callback_query
    # Delete the "Выберите тип задания" prompt entirely
    await query.message.delete()
    txt = "Пожалуйста, сделайте репост нашего канала @ambsharing в одном из чатов ниже:"
    now = datetime.now()
    cursor.execute(
        "INSERT INTO tasks (user_id, task_type, task_description, created_at) VALUES (?, ?, ?, ?)",
        (query.from_user.id, 'repost', txt, now)
    )
    conn.commit()
    # bump pending task count for user
    cursor.execute("UPDATE users SET pending_tasks = pending_tasks + 1 WHERE user_id = ?", (query.from_user.id,))
    conn.commit()
    cursor.execute("SELECT chat_username FROM allowed_chats ORDER BY RANDOM()")
    chats = [row[0] for row in cursor.fetchall()]
    text = txt + "\n\n" + "\n".join(chats)
    keyboard = [[InlineKeyboardButton("✅ Я выполнил", callback_data='task_done')]]
    await query.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def handle_task_back(update, context):
    query = update.callback_query
    # 1) Подтверждаем нажатие и убираем текущие кнопки
    await query.answer()
    chat_id = query.message.chat.id
    await query.message.delete()

    # 2) Удаляем предыдущее сообщение — либо мем, либо текст
    for key in ('last_task_msg_id', 'last_meme_msg_id', 'last_task_content_msg_id'):
        msg_id = context.user_data.pop(key, None)
        if msg_id:
            try:
                await context.bot.delete_message(chat_id=chat_id, message_id=msg_id)
            except:
                pass

async def handle_task_done(update, context):
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat.id

    # 1) Сначала отправляем пользователю запрос на скриншот
    context.user_data['awaiting_screenshot'] = True
    prompt = await context.bot.send_message(
        chat_id=chat_id,
        text="📸 <b>Пришлите скриншот выполнения задания</b>",
        parse_mode=ParseMode.HTML
    )
    context.user_data['screenshot_prompt_id'] = prompt.message_id

    # 2) И только после этого удаляем старые сообщения с мемом/текстом и кнопками
    for key in ('last_task_msg_id', 'last_meme_msg_id', 'last_task_content_msg_id'):
        msg_id = context.user_data.pop(key, None)
        if msg_id:
            try:
                await context.bot.delete_message(chat_id=chat_id, message_id=msg_id)
            except:
                pass


# --- MAIN SCREEN HANDLER ---
async def main_screen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await send_main_reply_keyboard(update, context)

async def handle_screenshot(update, context):
    # Only process screenshots if user was prompted
    if not context.user_data.get('awaiting_screenshot'):
        return
    # Clear the flag so only the first photo is processed
    context.user_data['awaiting_screenshot'] = False
    # delete the screenshot prompt and the user’s photo message
    prompt_id = context.user_data.pop('screenshot_prompt_id', None)
    if prompt_id:
        await context.bot.delete_message(
            chat_id=update.effective_chat.id,
            message_id=prompt_id
        )
    await update.message.delete()
    user = update.effective_user
    # Принимаем либо фото, либо файл-изображение
    photo_file = None
    if update.message.photo:
        photo_file = await update.message.photo[-1].get_file()
    elif update.message.document and update.message.document.mime_type.startswith('image/'):
        photo_file = await update.message.document.get_file()
    else:
        return
    # find latest pending task
    cursor.execute(
        "SELECT task_id FROM tasks WHERE user_id = ? AND status = 'pending' ORDER BY created_at DESC LIMIT 1",
        (user.id,)
    )
    row = cursor.fetchone()
    if not row:
        await update.message.reply_text("Нет активных заданий.")
        return
    task_id = row[0]
    # save photo
    os.makedirs(SCREENSHOTS_DIR, exist_ok=True)
    path = os.path.join(SCREENSHOTS_DIR, f"{task_id}.jpg")
    await photo_file.download_to_drive(path)
    cursor.execute(
        "UPDATE tasks SET screenshot_path = ?, status = 'awaiting_review' WHERE task_id = ?",
        (path, task_id)
    )
    conn.commit()
    # confirm receipt to user
    await update.message.reply_text(
        "*🔥GOOD! Следи за кол-во пришедших рефералов в профиле!*\n\n"
        "_🤨Не хватает на купон?!_\n"
        "*🗣️Выполни еще заданий или пригласи друга!*",
        parse_mode=ParseMode.MARKDOWN
    )
    # Notify admins of new submission
    for admin_id in ADMIN_IDS:
        try:
            with open(path, 'rb') as photo:
                caption = (
                    f"📥 <b>Новая заявка от @{user.username or user.id}</b>\n"
                    f"ID задания: {task_id}"
                )
                keyboard = InlineKeyboardMarkup([
                    [InlineKeyboardButton("✅ Одобрить", callback_data=f'approve_task|{task_id}')],
                    [InlineKeyboardButton("❌ Отклонить", callback_data=f'decline_task|{task_id}')]
                ])
                photo_msg = await context.bot.send_photo(
                    chat_id=admin_id,
                    photo=photo,
                    caption=caption,
                    parse_mode=ParseMode.HTML,
                    reply_markup=keyboard
                )
                context.user_data['last_task_photo_msg_id'] = photo_msg.message_id
                context.user_data['last_task_photo_chat_id'] = admin_id
        except Exception:
            pass
    # show main reply keyboard
    # await send_main_reply_keyboard(update, context)


# --- ADMIN BROADCAST MESSAGE HANDLER ---
async def handle_admin_broadcast_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    mode = context.user_data.get('broadcast_mode')
    if not mode:
        return
    msg = update.message
    text = msg.text or msg.caption or ""
    photo = msg.photo[-1] if msg.photo else None
    sent, errors = 0, 0

    if mode == 'all':
        cursor.execute("SELECT user_id FROM users")
        for (uid,) in cursor.fetchall():
            try:
                if photo:
                    file = await photo.get_file()
                    os.makedirs(SCREENSHOTS_DIR, exist_ok=True)
                    path = os.path.join(SCREENSHOTS_DIR, f"bc_{uid}.jpg")
                    await file.download_to_drive(path)
                    await context.bot.send_photo(chat_id=uid, photo=open(path,'rb'), caption=text, parse_mode=ParseMode.HTML)
                else:
                    await context.bot.send_message(chat_id=uid, text=text, parse_mode=ParseMode.HTML)
                sent += 1
            except:
                errors += 1

    elif mode == 'user':
        parts = text.split(' ', 1)
        if len(parts) < 2:
            await update.message.reply_text("Неверный формат. Нужно: `@username текст`", parse_mode=ParseMode.HTML)
            return
        uname, body = parts
        cursor.execute("SELECT user_id FROM users WHERE username = ?", (uname.lstrip('@'),))
        row = cursor.fetchone()
        if not row:
            await update.message.reply_text("Пользователь не найден.")
            return
        uid = row[0]
        try:
            if photo:
                file = await photo.get_file()
                os.makedirs(SCREENSHOTS_DIR, exist_ok=True)
                path = os.path.join(SCREENSHOTS_DIR, f"bc_{uid}.jpg")
                await file.download_to_drive(path)
                await context.bot.send_photo(chat_id=uid, photo=open(path,'rb'), caption=body, parse_mode=ParseMode.HTML)
            else:
                await context.bot.send_message(chat_id=uid, text=body, parse_mode=ParseMode.MARKDOWN_V2)
            sent = 1
        except:
            errors = 1

    context.user_data['broadcast_mode'] = None
    await update.message.reply_text(f"Рассылка завершена: {sent} успешно, {errors} ошибок.")


# --- ADMIN BROADCAST FLOW INPUT HANDLER ---
async def handle_admin_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user.id not in ADMIN_IDS:
        return
    
    if update.message.text == "Статистика":
        await stats_command(update, context)
        return

    # Текущее состояние админ-флоу по контенту
    content_stage = context.user_data.get('content_stage')
    stage = context.user_data.get('task_stage')

    # Approve: await promo code
    if stage == 'await_promo_code' and update.message.text:
        # delete the bot's prompt message
        prompt_id = context.user_data.pop('promo_prompt_msg_id', None)
        if prompt_id:
            await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=prompt_id)
        # delete the admin's response message
        await update.message.delete()
        code = update.message.text.strip()
        task_id = context.user_data['task_id']
        user_id = context.user_data['task_user_id']
        # update task status
        cursor.execute("UPDATE tasks SET status='approved' WHERE task_id = ?", (task_id,))
        # update user counters
        cursor.execute(
            "UPDATE users SET pending_tasks = pending_tasks - 1, completed_tasks = completed_tasks + 1 WHERE user_id = ?",
            (user_id,)
        )
        conn.commit()
        # save coupon
        cursor.execute("INSERT INTO coupons (code, type) VALUES (?, ?)", (code, 'promo'))
        conn.commit()
        # notify user
        await context.bot.send_message(chat_id=user_id,
                                       text=f"🎉 Поздравляем! Ваш купон: {code}")
        # now send updated profile to user
        cursor.execute("SELECT username, first_name, last_name FROM users WHERE user_id = ?", (user_id,))
        uname, first_name, last_name = cursor.fetchone()
        cursor.execute("SELECT COUNT(*) FROM tasks WHERE user_id = ? AND status = 'approved'", (user_id,))
        completed = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM tasks WHERE user_id = ? AND status = 'pending'", (user_id,))
        pending = cursor.fetchone()[0]
        profile_text = (
            "*💼ПРОФИЛЬ:*\n\n"
            f"*👤 User:* _@{uname}_\n"
            f"*🪪 ID:* _{user_id}_\n\n"
            f"*🔥 Заданий выполнено:* {completed}\n"
            f"*⏳ Заданий на проверке:* {pending}"
        )
        await context.bot.send_message(chat_id=user_id,
                                       text=profile_text,
                                       parse_mode=ParseMode.MARKDOWN,
                                       reply_markup=back_inline_markup)
        await update.message.reply_text("Купон отправлен пользователю.", reply_markup=back_inline_markup)
        context.user_data['task_stage'] = None
        return

    # Decline: await reason
    if stage == 'await_decline_reason' and update.message.text:
        reason = update.message.text.strip()
        task_id = context.user_data['task_id']
        user_id = context.user_data['task_user_id']
        cursor.execute("UPDATE tasks SET status='declined' WHERE task_id = ?", (task_id,))
        # decrement pending tasks on decline
        cursor.execute(
            "UPDATE users SET pending_tasks = pending_tasks - 1 WHERE user_id = ?",
            (user_id,)
        )
        conn.commit()
        await context.bot.send_message(chat_id=user_id,
                                       text=f"❌ Ваше задание отклонено.\nПричина: {reason}")
        # now send updated profile to user
        cursor.execute("SELECT username, first_name, last_name FROM users WHERE user_id = ?", (user_id,))
        uname, first_name, last_name = cursor.fetchone()
        cursor.execute("SELECT COUNT(*) FROM tasks WHERE user_id = ? AND status = 'approved'", (user_id,))
        completed = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM tasks WHERE user_id = ? AND status = 'pending'", (user_id,))
        pending = cursor.fetchone()[0]
        profile_text = (
            "*💼ПРОФИЛЬ:*\n\n"
            f"*👤 User:* _@{uname}_\n"
            f"*🪪 ID:* _{user_id}_\n\n"
            f"*🔥 Заданий выполнено:* {completed}\n"
            f"*⏳ Заданий на проверке:* {pending}"
        )
        await context.bot.send_message(chat_id=user_id,
                                       text=profile_text,
                                       parse_mode=ParseMode.MARKDOWN,
                                       reply_markup=back_inline_markup)
        await update.message.reply_text("Причина отклонения отправлена пользователю.", reply_markup=back_inline_markup)
        context.user_data['task_stage'] = None
        return

    # -- Добавление мема: сразу сохраняем файл, без текста --
    if content_stage == CONTENT_STAGE_ADD_MEME and update.message and update.message.photo:
        photo = update.message.photo[-1]
        file = await photo.get_file()
        os.makedirs(MEMES_DIR, exist_ok=True)
        path = os.path.join(MEMES_DIR, f"meme_{file.file_id}.jpg")
        await file.download_to_drive(path)
        # Сохраняем в БД с пустым текстом
        cursor.execute(
            "INSERT INTO meme_templates (file_path, text) VALUES (?, ?)",
            (path, "")
        )
        conn.commit()
        await update.message.reply_text("✅ Мем добавлен.", reply_markup=back_inline_markup)
        context.user_data['content_stage'] = None
        return

    # Handle deletion of meme by ID
    if content_stage == CONTENT_STAGE_DELETE_MEME and update.message and update.message.text:
        text = update.message.text.strip()
        if text.isdigit():
            meme_id = int(text)
            cursor.execute("DELETE FROM meme_templates WHERE id = ?", (meme_id,))
            conn.commit()
            await update.message.reply_text("✅ Мем удалён.", reply_markup=back_inline_markup)
            context.user_data['content_stage'] = None
        else:
            await update.message.reply_text("❌ Некорректный ID. Пришлите номер мема для удаления.", reply_markup=back_inline_markup)
        return
    # Handle adding a new chat with validation
    if content_stage == CONTENT_STAGE_ADD_CHAT and update.message and update.message.text:
        chat = update.message.text.strip()
        # Validate format: must start with '@', 't.me/' or 'http'
        if not (chat.startswith('@') or chat.startswith('t.me/') or chat.startswith('http')):
            await update.message.reply_text(
                "❌ Некорректный формат. Введите @username, t.me/... или полную ссылку на чат.",
                reply_markup=back_inline_markup
            )
            return
        # Save to database
        cursor.execute("INSERT OR IGNORE INTO allowed_chats (chat_username) VALUES (?)", (chat,))
        conn.commit()
        await update.message.reply_text(f"✅ Чат {chat} добавлен.", reply_markup=back_inline_markup)
        context.user_data['content_stage'] = None
        return

    # Handle deletion of chat by number
    if content_stage == CONTENT_STAGE_DELETE_CHAT and update.message and update.message.text.isdigit():
        idx = int(update.message.text.strip()) - 1
        chats = context.user_data.get('delete_chats_list', [])
        if 0 <= idx < len(chats):
            removed = chats[idx]
            cursor.execute("DELETE FROM allowed_chats WHERE chat_username = ?", (removed,))
            conn.commit()
            await update.message.reply_text(f"✅ Чат {removed} удалён.", reply_markup=back_inline_markup)
        else:
            await update.message.reply_text("❌ Некорректный номер. Пришлите число из списка.", reply_markup=back_inline_markup)
        # Clean up
        context.user_data.pop('delete_chats_list', None)
        context.user_data['content_stage'] = None
        return

    # Handle adding a new promo offer
    if context.user_data.get('promo_stage') == PROMO_STAGE_ADD and update.message and update.message.text:
        text = update.message.text.strip()
        if '—' in text:
            title, cost_str = [s.strip() for s in text.split('—', 1)]
            if cost_str.isdigit():
                cost = int(cost_str)
                cursor.execute("INSERT INTO promo_offers (title, cost) VALUES (?, ?)", (title, cost))
                conn.commit()
                await update.message.reply_text(f"✅ Оффер '{title}' за {cost} преданных добавлен.", reply_markup=back_inline_markup)
                context.user_data['promo_stage'] = None
            else:
                await update.message.reply_text("❌ Неверная стоимость. Введите целое число после —.", reply_markup=back_inline_markup)
        else:
            await update.message.reply_text("❌ Неверный формат. Используйте: Название — стоимость", reply_markup=back_inline_markup)
        return

    # Handle deletion of promo offer by ID
    if context.user_data.get('promo_stage') == PROMO_STAGE_DELETE and update.message and update.message.text.isdigit():
        oid = int(update.message.text.strip())
        cursor.execute("DELETE FROM promo_offers WHERE offer_id = ?", (oid,))
        conn.commit()
        await update.message.reply_text(f"✅ Оффер {oid} удалён.", reply_markup=back_inline_markup)
        context.user_data['promo_stage'] = None
        return

    # Handle deletion of text template by ID
    if context.user_data.get('content_stage') == CONTENT_STAGE_LIST_TEXTS and update.message and update.message.text:
        text_id = update.message.text.strip()
        if text_id.isdigit():
            tid = int(text_id)
            cursor.execute("DELETE FROM text_templates WHERE id = ?", (tid,))
            conn.commit()
            await update.message.reply_text("✅ Текст удалён.", reply_markup=back_inline_markup)
            context.user_data['content_stage'] = None
        else:
            await update.message.reply_text("❌ Некорректный ID. Пришлите корректный номер текста.", reply_markup=back_inline_markup)
        return

    # Handle adding a new text template (preserve HTML formatting)
    if content_stage == CONTENT_STAGE_ADD_TEXT and update.message:
        # Preserve any HTML formatting sent by the admin
        text = getattr(update.message, "text_html", None) or update.message.text or ""
        cursor.execute(
            "INSERT INTO text_templates (text) VALUES (?)",
            (text,)
        )
        conn.commit()
        await update.message.reply_text("✅ Текст добавлен.", reply_markup=back_inline_markup)
        context.user_data['content_stage'] = None
        return
    stage_bc = context.user_data.get('broadcast_stage')
    if stage_bc == BROADCAST_STAGE_TEXT and update.message.text:
        text = update.message.text
        context.user_data['broadcast_text'] = text
        await update.message.delete()
        # Offer next steps
        await update.message.reply_text(
            f"Текст рассылки:\n{text}",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Прикрепить фото", callback_data='bc_attach_photo')],
                [InlineKeyboardButton("Продолжить", callback_data='bc_send_confirm')],
                [InlineKeyboardButton("🔙 Назад", callback_data='task_back')],
            ]),
            parse_mode=ParseMode.HTML
        )
    elif stage_bc == BROADCAST_STAGE_PHOTO and update.message.photo:
        photo = update.message.photo[-1]
        file = await photo.get_file()
        os.makedirs("screenshots", exist_ok=True)
        path = "screenshots/broadcast_photo.jpg"
        await file.download_to_drive(path)
        context.user_data['broadcast_photo'] = path
        await update.message.delete()
        await update.message.reply_text(
            "Фото сохранено. Готовы отправить рассылку?",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Да", callback_data='bc_execute')],
                [InlineKeyboardButton("🔙 Назад", callback_data='task_back')],
            ]),
            parse_mode=ParseMode.MARKDOWN_V2
        )

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("У вас нет прав для использования этой команды.")
        return

    if not context.args:
        await update.message.reply_text("Использование: /broadcast <сообщение>")
        return

    message = ' '.join(context.args)
    cursor.execute("SELECT user_id FROM users")
    users = cursor.fetchall()
    count = 0
    for (uid,) in users:
        try:
            await context.bot.send_message(chat_id=uid, text=message, parse_mode=ParseMode.MARKDOWN_V2)
            count += 1
        except Exception as e:
            logger.warning(f"Не удалось отправить сообщение пользователю {uid}: {e}")
    await update.message.reply_text(f"Сообщение отправлено {count} пользователям.")

# ——— ОБРАБОТЧИК СТАТИСТИКИ ———
async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        return

    now = datetime.now()
    today_start = datetime(now.year, now.month, now.day)
    week_start = today_start - timedelta(days=now.weekday())

    # Всего пользователей
    cursor.execute("SELECT COUNT(*) FROM users")
    total = cursor.fetchone()[0]

    # Пришло сегодня
    cursor.execute(
        "SELECT COUNT(*) FROM users WHERE joined_date >= ?",
        (today_start.isoformat(),)
    )
    today_count = cursor.fetchone()[0]

    # Пришло за неделю
    cursor.execute(
        "SELECT COUNT(*) FROM users WHERE joined_date >= ?",
        (week_start.isoformat(),)
    )
    week_count = cursor.fetchone()[0]

    text = (
        "Статистика AMB Bot:\n\n"
        f"➖<b>Прибавилось сегодня:</b> {today_count}\n\n"
        f"➖<b>Прибавилось за неделю:</b> {week_count}\n\n"
        f"🤙<b>Всего:</b> {total}"
    )
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("Получить файл", callback_data='get_users_file')
    ]])
    await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=keyboard)

async def send_users_file_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user_id = query.from_user.id
    if user_id not in ADMIN_IDS:
        await query.answer("Нет доступа", show_alert=True)
        return
    await query.answer()

    # Получаем список пользователей
    cursor.execute("SELECT user_id, username, first_name, last_name, ref_by, joined_date FROM users")
    rows = cursor.fetchall()

    # Готовим CSV
    export_dir = "exports"
    os.makedirs(export_dir, exist_ok=True)
    filename = f"users_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    path = os.path.join(export_dir, filename)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["user_id", "username", "first_name", "last_name", "ref_by", "joined_date"])
        writer.writerows(rows)

    # Отправляем файл админу
    with open(path, "rb") as f:
        await query.message.reply_document(document=f, filename=filename)

def main() -> None:
    job_queue = JobQueue()
    application = ApplicationBuilder().token(TOKEN).job_queue(job_queue).build()
    # 1. CommandHandler registrations
    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('profile', profile))
    application.add_handler(CommandHandler('broadcast', broadcast))
    # 2. CallbackQueryHandler registrations
    application.add_handler(CallbackQueryHandler(button_handler), group=1)
    application.add_handler(
        CallbackQueryHandler(check_subscription_handler, pattern='^check_subscription$')
    )
    application.add_handler(
        CallbackQueryHandler(promo_choose_handler, pattern='^promo_choose$')
    )
    application.add_handler(
        CallbackQueryHandler(promo_back_handler, pattern='^promo_back$')
    )
    application.add_handler(
        CallbackQueryHandler(promo_offer_handler, pattern=r'^promo_offer\|\d+$')
    )
    application.add_handler(
        CallbackQueryHandler(promo_confirm_handler, pattern=r'^promo_confirm\|\d+$')
    )
    application.add_handler(
        CallbackQueryHandler(
            send_users_file_handler,
            pattern=r'^get_users_file$'
        )
    )
    # 3. MessageHandler(filters.Regex(...)) for admin reply-keyboard buttons (in order)
    # 1. "Админ", "Главная", "Контент", "Промо", "Купоны", "Статистика", "Рассылка"
    application.add_handler(MessageHandler(filters.Regex('^Админ$'), admin_panel))
    application.add_handler(MessageHandler(filters.Regex('^Главная$'), main_button_handler))
    application.add_handler(MessageHandler(filters.Regex(r'^Контент$') & filters.User(ADMIN_IDS), content_command))
    application.add_handler(MessageHandler(filters.Regex(r'^Промо$') & filters.User(ADMIN_IDS), promo_panel))
    # "Купоны" button is not explicitly handled above; if needed, add here.
    application.add_handler(
        MessageHandler(
            filters.Regex(r'^Купоны$') & filters.User(ADMIN_IDS),
            lambda update, context: None  # Placeholder if handler exists
        )
    )
    application.add_handler(
        MessageHandler(
            filters.Regex(r'^Статистика$') & filters.User(ADMIN_IDS),
            stats_command
        )
    )
    application.add_handler(MessageHandler(filters.Regex(r'^Рассылка$'), broadcast_panel))

    # 2. Content submenu
    application.add_handler(
        MessageHandler(filters.Regex(r'^📥 Добавить мем$') & filters.User(ADMIN_IDS), content_add_meme_handler)
    )
    application.add_handler(
        MessageHandler(filters.Regex(r'^🗑 Удалить мем$') & filters.User(ADMIN_IDS), content_delete_meme_handler)
    )
    application.add_handler(
        MessageHandler(filters.Regex(r'^📋 Список чатов$') & filters.User(ADMIN_IDS), content_list_chats_handler)
    )
    application.add_handler(
        MessageHandler(filters.Regex(r'^➕ Добавить чат$') & filters.User(ADMIN_IDS), content_add_chat_handler)
    )
    application.add_handler(
        MessageHandler(filters.Regex(r'^🗑 Удалить чат$') & filters.User(ADMIN_IDS), content_delete_chat_handler)
    )
    application.add_handler(
        MessageHandler(filters.Regex(r'^✍️ Добавить текст$') & filters.User(ADMIN_IDS), content_add_text_handler)
    )
    application.add_handler(
        MessageHandler(filters.Regex(r'^🧾 Список текстов$') & filters.User(ADMIN_IDS), content_list_texts_handler)
    )
    application.add_handler(
        MessageHandler(filters.Regex(r'^🔙 Назад$') & filters.User(ADMIN_IDS), admin_panel)
    )

    # 3. Promo submenu
    application.add_handler(
        MessageHandler(filters.Regex(r'^📥 Добавить оффер$') & filters.User(ADMIN_IDS), promo_add_offer_handler)
    )
    application.add_handler(
        MessageHandler(filters.Regex(r'^🗑 Удалить оффер$') & filters.User(ADMIN_IDS), promo_delete_offer_handler)
    )
    application.add_handler(
        MessageHandler(filters.Regex(r'^📋 Список офферов$') & filters.User(ADMIN_IDS), promo_list_offers_handler)
    )

    # 4. User menu: "Задания", "👤 Профиль", "ℹ️ Правила", "🛠 Поддержка", "🔥Получить ПРОМО", "✅Ввести ПРОМО"
    application.add_handler(
        MessageHandler(filters.Regex(r'^Задания$'), show_participate_menu)
    )
    application.add_handler(MessageHandler(filters.Regex('^👤 Профиль$'), profile))
    application.add_handler(MessageHandler(filters.Regex('^ℹ️ Правила$'), rules_handler))
    application.add_handler(MessageHandler(filters.Regex('^🛠 Поддержка$'), support_handler))
    application.add_handler(
        MessageHandler(filters.Regex(r'^🔥Получить ПРОМО$'), promo_user_start)
    )
    # Conversation для ввода промокода
    promo_conv = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex(r'^✅Ввести ПРОМО$'), prompt_promo_code)
        ],
        states={
            ENTER_CODE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_promo_code)
            ]
        },
        fallbacks=[],
        per_user=True,
        per_chat=True
    )
    application.add_handler(promo_conv)

    # Handle admin "Проверить задания" via text messages (if needed)
    application.add_handler(
        MessageHandler(
            filters.Regex('^Проверить задание$') & filters.User(ADMIN_IDS),
            check_tasks_command
        )
    )

    # 5. After all specific handlers, add the generic broadcast and admin-input handlers
    application.add_handler(
        MessageHandler(filters.TEXT & filters.User(ADMIN_IDS), handle_admin_broadcast_message)
    )
    application.add_handler(
        MessageHandler(
            filters.ALL & filters.User(ADMIN_IDS) & ~filters.Regex('^Админ$'),
            handle_admin_input
        ),
        group=1
    )

    # 6. Finally, keep a single screenshot handler at the end
    application.add_handler(
        MessageHandler(
            filters.PHOTO | filters.Document.IMAGE,
            handle_screenshot
        )
    )
    application.add_handler(CommandHandler("clear", clear_chat))

    application.run_polling()

# --- RULES HANDLER ---
async def rules_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # Delete user's pressed button message
    await update.message.delete()
    # Send rules
    await update.message.reply_text(
        rules_text,
        parse_mode=ParseMode.HTML,
        reply_markup=back_inline_markup
    )

# --- SUPPORT HANDLER ---
async def support_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.delete()
    await update.message.reply_text(
        "По вопросам: @amb_managers",
        reply_markup=back_inline_markup
    )

# --- MAIN BUTTON HANDLER ---
async def main_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.delete()
    await send_main_reply_keyboard(update, context)

# --- MAIN REPLY KEYBOARD HANDLER ---
async def send_main_reply_keyboard(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # Delete previous main-screen message if exists
    prev = context.user_data.get('last_main_msg')
    if prev:
        try:
            await context.bot.delete_message(chat_id=prev['chat_id'], message_id=prev['message_id'])
        except:
            pass
    context.user_data['last_main_msg'] = None
    user_id = update.effective_user.id
    buttons = [
        [KeyboardButton("Задания")],
        [KeyboardButton("👤 Профиль"), KeyboardButton("ℹ️ Правила"), KeyboardButton("🛠 Поддержка")],
        [KeyboardButton("🔥Получить ПРОМО"), KeyboardButton("✅Ввести ПРОМО")]
    ]
    if user_id in ADMIN_IDS:
        buttons.append([KeyboardButton("Админ")])
    reply_keyboard = ReplyKeyboardMarkup(buttons, resize_keyboard=True)
    # Determine where to send
    if hasattr(update, "callback_query") and update.callback_query:
        target = update.callback_query.message
    else:
        target = update.message
    main_msg = await target.reply_text(
        "<b>🛑Стой-стой-стой..</b>\n"
        "👉У тебя есть <b>ПРОМОКОД</b>⁉️\n\n"
        "<b>Введи его и получи подарок!</b>\n\n"
        "⬇️ Жми на кнопку \"✅Ввести ПРОМО\" ⬇️\n",
        parse_mode=ParseMode.HTML,
        reply_markup=reply_keyboard
    )
    # Save main-screen message for later deletion
    context.user_data['last_main_msg'] = {
        'chat_id': main_msg.chat_id,
        'message_id': main_msg.message_id
    }

if __name__ == '__main__':
    main()

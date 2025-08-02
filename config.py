import os
import logging

# Настройки логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', 
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Токен бота
TOKEN = "8284588833:AAGmxhM-yggPhmAupV6kfEKIJ2Q3OJYuhRU"

# ID администраторов
ADMIN_IDS = [6798547914]

# ID канала для проверки подписки
CHANNEL_ID = -1002090905218

# Пути к файлам
BASE_DIR = os.environ.get("BASE_DIR", os.path.dirname(__file__))
DB_PATH = os.environ.get("DB_PATH", os.path.join(BASE_DIR, "bot_database.db"))
REMINDER_IMAGE_PATH = os.path.join(BASE_DIR, "reminder.png")
WELCOME_IMAGE_PATH = os.path.join(BASE_DIR, "welcome.jpg")
STATIC_DIR = os.environ.get("STATIC_DIR", BASE_DIR)
MEMES_DIR = os.path.join(BASE_DIR, "memes")
SCREENSHOTS_DIR = os.path.join(BASE_DIR, "screenshots")

# Текст правил
RULES_TEXT = (
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

# Состояния для админских флоу
BROADCAST_STAGE_TEXT = 'await_text'
BROADCAST_STAGE_PHOTO = 'await_photo'
BROADCAST_STAGE_CONFIRM = 'await_confirm'

# Состояния для контент-флоу
CONTENT_STAGE_ADD_MEME = 'add_meme'
CONTENT_STAGE_MEME_CAPTION = 'meme_caption'
CONTENT_STAGE_DELETE_MEME = 'delete_meme'
CONTENT_STAGE_ADD_TEXT = 'add_text'
CONTENT_STAGE_LIST_TEXTS = 'list_texts'
CONTENT_STAGE_LIST_CHATS = 'list_chats'
CONTENT_STAGE_ADD_CHAT = 'add_chat'
CONTENT_STAGE_DELETE_CHAT = 'delete_chat'

# Состояния для промо-флоу
PROMO_STAGE_ADD = 'add_offer'
PROMO_STAGE_DELETE = 'delete_offer'

# Состояние для ввода промокода
ENTER_CODE = 1 
import os
from datetime import datetime, timedelta
from config import CHANNEL_ID, logger

# Кэш для результатов проверки подписки
_subscription_cache = {}
_cache_timeout = 30  # 30 секунд (для быстрого обновления)

def make_chat_url(raw: str) -> str:
    """Нормализация URL чата"""
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

def reset_broadcast_state(context):
    """Сброс состояния рассылки"""
    for key in ['broadcast_stage', 'broadcast_mode', 'broadcast_text', 'broadcast_photo']:
        context.user_data.pop(key, None)

async def is_user_subscribed(bot, user_id: int) -> bool:
    """Проверка подписки пользователя на канал - МГНОВЕННАЯ"""
    try:
        # Мгновенная проверка статуса пользователя в канале
        member = await bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        return member.status in ('member', 'creator', 'administrator')
        
    except Exception as e:
        logger.error(f"Subscription check failed for user {user_id}: {e}")
        return False

async def force_check_subscription(bot, user_id: int) -> bool:
    """Принудительная проверка подписки без использования кэша - МГНОВЕННАЯ"""
    try:
        # Мгновенная проверка статуса пользователя в канале
        member = await bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        return member.status in ('member', 'creator', 'administrator')
        
    except Exception as e:
        logger.error(f"Force subscription check failed for user {user_id}: {e}")
        return False

def clear_subscription_cache(user_id: int = None):
    """Очистка кэша подписки"""
    global _subscription_cache
    if user_id is None:
        # Очищаем весь кэш
        _subscription_cache.clear()
        logger.info("Subscription cache cleared")
    else:
        # Очищаем кэш для конкретного пользователя
        cache_key = f"{user_id}_{CHANNEL_ID}"
        if cache_key in _subscription_cache:
            del _subscription_cache[cache_key]
            logger.info(f"Subscription cache cleared for user {user_id}")

async def debug_subscription(bot, user_id: int) -> dict:
    """Диагностика проблем с подпиской"""
    debug_info = {
        'user_id': user_id,
        'channel_id': CHANNEL_ID,
        'bot_can_access_channel': False,
        'channel_info': None,
        'user_status': None,
        'error': None
    }
    
    try:
        # Проверяем доступ бота к каналу
        chat_info = await bot.get_chat(CHANNEL_ID)
        debug_info['bot_can_access_channel'] = True
        debug_info['channel_info'] = {
            'id': chat_info.id,
            'title': chat_info.title,
            'type': chat_info.type,
            'username': getattr(chat_info, 'username', None)
        }
        
        # Проверяем статус пользователя
        member = await bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        debug_info['user_status'] = {
            'status': member.status,
            'is_member': member.status in ('member', 'creator', 'administrator'),
            'until_date': getattr(member, 'until_date', None),
            'is_member_status': member.status == 'member',
            'is_creator_status': member.status == 'creator',
            'is_admin_status': member.status == 'administrator'
        }
        
    except Exception as e:
        debug_info['error'] = str(e)
        logger.error(f"Debug subscription failed: {e}")
    
    return debug_info

def format_profile_text(user_stats, user_id, username):
    """Форматирование текста профиля"""
    available = max(0, user_stats['loyal_referrals'] - user_stats['used_loyal'])  # Защита от отрицательных значений
    
    return (
        "<b>💼ПРОФИЛЬ:</b>\n\n"
        f"<b>👤 User:</b> @{username or 'нет'}\n"
        f"<b>🆔 ID:</b> {user_id}\n\n"
        f"<b>💰 Твои рефералы:</b> {user_stats['referrals_count']}\n"
        f"<b>💕ПРЕДАННЫЕ РЕФЕРАЛЫ:</b> {available}\n"
        f"<b>💔 Потрачено 💖:</b> {user_stats['used_loyal']}\n\n"
        f"<b>🔥 Заданий выполнено:</b> {user_stats['completed_tasks']}\n"
        f"<b>⏳ Заданий на проверке:</b> {user_stats['pending_tasks']}\n\n"
        f"<b>🔑 Ваш промокод:</b> <code>{user_stats['promo_code']}</code>\n\n"
        "<b>🔗 Твоя реф-ссылка:</b>\n"
        f"<a href=\"https://t.me/AMB_Promo_bot?start=ref_{user_id}\">https://t.me/AMB_Promo_bot?start=ref_{user_id}</a>"
    )

def format_task_panel(promo_code: str) -> str:
    """Форматирование панели задания с промокодом"""
    return (
        "🔎 Ищи в поиске @AMB_Promo_bot и\n"
        f"‼️ Вводи этот <b>ПРОМО:</b> <code>{promo_code}</code>\n"
        "🎁 И получи свой <b>ПОДАРОК</b>"
    )

def format_task_text(template_text: str, promo_code: str) -> str:
    """Форматирование текста задания с промокодом"""
    return (
        f"{template_text}\n\n"  # шаблон администратора
        "🔎 Ищи в поиске @AMB_Promo_bot и\n"
        f"‼️ Вводи этот <b>ПРОМО:</b> <code>{promo_code}</code>\n"
        "🎁 И получи свой <b>ПОДАРОК</b>"
    )

def get_welcome_caption() -> str:
    """Получение текста приветствия"""
    return (
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

def get_main_screen_text() -> str:
    """Получение текста главного экрана"""
    return (
        "<b>🛑Стой-стой-стой..</b>\n"
        "👉У тебя есть <b>ПРОМОКОД</b>⁉️\n\n"
        "<b>Введи его и получи подарок!</b>\n\n"
        "⬇️ Жми на кнопку \"✅Ввести ПРОМО\" ⬇️\n"
    )

def get_gift_text(gift_code: str = "QODMSH") -> str:
    """Получение текста подарка"""
    return (
        "🎁<b>ТВОЙ ПОДАРОК</b>\n\n"
        "👉<i>Промокод на сервис ЮРЕНТ</i>👈\n\n"
        f"🎫<b>ПРОМО:</b> <code>{gift_code}</code>\n"
        "(⬆️нажми на код чтобы скопировать⬆️)\n\n"
        "<i>Дает</i> <b>СКИДКУ В 50%</b> <i>на первые 2 поездки</i>"
    )

def get_subscription_text() -> str:
    """Получение текста проверки подписки"""
    return (
        "<b>✌️Привет!</b>\n\n"
        "<i>🔸Прежде чем двинемся дальше,\n"
        "подпишись на наш закрытый канал.</i>\n\n"
        "<b>Там вся движуха, инсайды и секретные фишки!</b>\n\n"
        "<b>☞https://t.me/+_C0oLC4YtHo2OGFi</b>"
    )

def get_reminder_text() -> str:
    """Получение текста напоминания"""
    return (
        "⏱ <b>Ждать 3 дня? Зачем?</b>\n"
        "Промо можно взять <b>прямо сейчас</b>:\n\n"
        '<a href="https://t.me/Kicksheringboss_bot?start=start">Жми сюда</a>'
    )

def get_stats_text(today_count: int, week_count: int, total: int) -> str:
    """Форматирование статистики"""
    return (
        "Статистика AMB Bot:\n\n"
        f"➖<b>Прибавилось сегодня:</b> {today_count}\n\n"
        f"➖<b>Прибавилось за неделю:</b> {week_count}\n\n"
        f"🤙<b>Всего:</b> {total}"
    )

def ensure_directories():
    """Создание необходимых директорий"""
    directories = ['memes', 'screenshots', 'exports']
    for directory in directories:
        os.makedirs(directory, exist_ok=True)

def parse_start_parameter(text: str) -> int:
    """Парсинг параметра start команды"""
    if not text.startswith('/start'):
        return None
    
    parts = text.split(' ', 1)
    if len(parts) <= 1:
        return None
    
    param = parts[1]
    if param.startswith('ref_'):
        try:
            return int(param[4:])
        except ValueError:
            return None
    else:
        try:
            return int(param)
        except ValueError:
            return None

def get_date_range():
    """Получение диапазона дат для статистики"""
    now = datetime.now()
    today_start = datetime(now.year, now.month, now.day)
    week_start = today_start - timedelta(days=now.weekday())
    return today_start, week_start

# Добавляем недостающие константы для совместимости
BROADCAST_STAGE_TEXT = 'await_text'
BROADCAST_STAGE_PHOTO = 'await_photo'
BROADCAST_STAGE_CONFIRM = 'await_confirm'

CONTENT_STAGE_ADD_MEME = 'add_meme'
CONTENT_STAGE_MEME_CAPTION = 'meme_caption'
CONTENT_STAGE_DELETE_MEME = 'delete_meme'
CONTENT_STAGE_ADD_TEXT = 'add_text'
CONTENT_STAGE_LIST_TEXTS = 'list_texts'
CONTENT_STAGE_LIST_CHATS = 'list_chats'
CONTENT_STAGE_ADD_CHAT = 'add_chat'
CONTENT_STAGE_DELETE_CHAT = 'delete_chat'

PROMO_STAGE_ADD = 'add_offer'
PROMO_STAGE_DELETE = 'delete_offer' 
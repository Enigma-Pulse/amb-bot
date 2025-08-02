from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton

# Основные инлайн клавиатуры
def get_main_inline_keyboard():
    """Основная инлайн клавиатура"""
    keyboard = [
        [InlineKeyboardButton("🚀 Участвовать", callback_data='participate')],
        [InlineKeyboardButton("👤 Профиль", callback_data='profile')],
        [InlineKeyboardButton("ℹ️ Правила", callback_data='rules')],
        [InlineKeyboardButton("🛠 Поддержка", callback_data='support')],
    ]
    return InlineKeyboardMarkup(keyboard)

def get_back_inline_keyboard():
    """Клавиатура с кнопкой "Назад" """
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Назад", callback_data='general_back')]])

def get_participate_keyboard():
    """Клавиатура выбора типа задания"""
    keyboard = [
        [InlineKeyboardButton("🧠 Мем", callback_data='task_meme')],
        [InlineKeyboardButton("🗣 Текст", callback_data='task_text')],
        [InlineKeyboardButton("🔙 Назад", callback_data='task_back')],
    ]
    return InlineKeyboardMarkup(keyboard)

def get_task_control_keyboard():
    """Клавиатура управления заданием"""
    keyboard = [
        InlineKeyboardButton("✅ Я выполнил", callback_data='task_done'),
        InlineKeyboardButton("🔙 Назад", callback_data='task_back'),
    ]
    return InlineKeyboardMarkup([keyboard])

def get_task_control_with_other_keyboard():
    """Клавиатура управления заданием с кнопкой "Другой" """
    keyboard = [
        InlineKeyboardButton("✅ Я выполнил", callback_data='task_done'),
        InlineKeyboardButton("🔙 Назад", callback_data='task_back'),
        InlineKeyboardButton("🔄 Другой", callback_data='task_other')
    ]
    return InlineKeyboardMarkup([keyboard])

def get_task_control_with_other_text_keyboard():
    """Клавиатура управления текстовым заданием с кнопкой "Другой" """
    keyboard = [
        InlineKeyboardButton("✅ Я выполнил", callback_data='task_done'),
        InlineKeyboardButton("🔙 Назад", callback_data='task_back'),
        InlineKeyboardButton("🔄 Другой", callback_data='task_other_text')
    ]
    return InlineKeyboardMarkup([keyboard])

def get_task_control_with_other_meme_keyboard():
    """Клавиатура управления мем-заданием с кнопкой "Другой" """
    keyboard = [
        InlineKeyboardButton("✅ Я выполнил", callback_data='task_done'),
        InlineKeyboardButton("🔙 Назад", callback_data='task_back'),
        InlineKeyboardButton("🔄 Другой", callback_data='task_other_meme')
    ]
    return InlineKeyboardMarkup([keyboard])

def get_broadcast_keyboard():
    """Клавиатура выбора режима рассылки"""
    keyboard = [
        [
            InlineKeyboardButton("Всем", callback_data='broadcast_all'),
            InlineKeyboardButton("Пользователю", callback_data='broadcast_user')
        ],
        [InlineKeyboardButton("🔙 Назад", callback_data='task_back')],
        [InlineKeyboardButton("❌ Отмена", callback_data='bc_cancel')]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_task_approval_keyboard(task_id):
    """Клавиатура одобрения/отклонения задания"""
    keyboard = [
        [InlineKeyboardButton("✅ Одобрить", callback_data=f'approve_task|{task_id}')],
        [InlineKeyboardButton("❌ Отклонить", callback_data=f'decline_task|{task_id}')]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_promo_choose_keyboard():
    """Клавиатура выбора промо"""
    return InlineKeyboardMarkup([[InlineKeyboardButton("😚Проверить", callback_data='promo_choose')]])

def get_promo_offers_keyboard(offers):
    """Клавиатура с промо-офферами"""
    keyboard = []
    for offer_id, title, cost in offers:
        keyboard.append([InlineKeyboardButton(f"{title} за {cost}💖", callback_data=f'promo_offer|{offer_id}')])
    keyboard.append([InlineKeyboardButton("🔙 Назад", callback_data='promo_back')])
    return InlineKeyboardMarkup(keyboard)

def get_promo_confirm_keyboard(offer_id):
    """Клавиатура подтверждения промо"""
    keyboard = [
        [InlineKeyboardButton("Да", callback_data=f'promo_confirm|{offer_id}')],
        [InlineKeyboardButton("Нет", callback_data='promo_back')]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_gift_keyboard():
    """Клавиатура получения подарка"""
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("👉ЗАБРАТЬ👈", callback_data='get_gift')
    ]])

def get_subscription_check_keyboard():
    """Клавиатура проверки подписки"""
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Проверить подписку", callback_data='check_subscription')
    ]])

def get_rules_accept_keyboard():
    """Клавиатура принятия правил"""
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("💡Прочитал", callback_data='start_accept_rules')
    ]])

def get_rules_final_accept_keyboard():
    """Клавиатура финального принятия правил"""
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✅Прочитал", callback_data='final_accept_rules')
    ]])

def get_users_file_keyboard():
    """Клавиатура получения файла пользователей"""
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("Получить файл", callback_data='get_users_file')
    ]])

# Reply клавиатуры
def get_main_reply_keyboard(is_admin=False):
    """Основная reply клавиатура"""
    buttons = [
        [KeyboardButton("Задания")],
        [KeyboardButton("👤 Профиль"), KeyboardButton("ℹ️ Правила"), KeyboardButton("🛠 Поддержка")],
        [KeyboardButton("🔥Получить ПРОМО"), KeyboardButton("✅Ввести ПРОМО")]
    ]
    if is_admin:
        buttons.append([KeyboardButton("Админ")])
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)

def get_admin_reply_keyboard():
    """Админская reply клавиатура"""
    buttons = [
        [KeyboardButton("Контент"), KeyboardButton("Купоны"), KeyboardButton("Статистика")],
        [KeyboardButton("Рассылка"), KeyboardButton("Промо")],
        [KeyboardButton("Главная")]
    ]
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)

def get_content_reply_keyboard():
    """Клавиатура управления контентом"""
    buttons = [
        [KeyboardButton("📥 Добавить мем"), KeyboardButton("🗑 Удалить мем")],
        [KeyboardButton("✍️ Добавить текст"), KeyboardButton("🧾 Список текстов")],
        [KeyboardButton("📋 Список чатов")],
        [KeyboardButton("➕ Добавить чат"), KeyboardButton("🗑 Удалить чат")],
        [KeyboardButton("🔙 Назад")]
    ]
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)

def get_promo_reply_keyboard():
    """Клавиатура управления промо"""
    buttons = [
        [KeyboardButton("📥 Добавить оффер"), KeyboardButton("🗑 Удалить оффер")],
        [KeyboardButton("📋 Список офферов")],
        [KeyboardButton("🔙 Назад")]
    ]
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True)

# Утилиты для создания клавиатур с чатами
def create_chat_keyboard(chats):
    """Создание клавиатуры со ссылками на чаты"""
    from utils import make_chat_url
    
    buttons = []
    for chat in chats:
        buttons.append([InlineKeyboardButton(text=chat, url=make_chat_url(chat))])
    return buttons

def create_task_keyboard_with_chats(chats, include_other=False, task_type=None):
    """Создание клавиатуры задания с чатами"""
    buttons = create_chat_keyboard(chats)
    
    # Добавляем кнопки управления
    control_buttons = [
        InlineKeyboardButton("✅ Я выполнил", callback_data='task_done'),
        InlineKeyboardButton("🔙 Назад", callback_data='task_back')
    ]
    
    if include_other:
        if task_type == 'text':
            control_buttons.append(InlineKeyboardButton("🔄 Другой", callback_data='task_other_text'))
        elif task_type == 'meme':
            control_buttons.append(InlineKeyboardButton("🔄 Другой", callback_data='task_other_meme'))
        else:
            control_buttons.append(InlineKeyboardButton("🔄 Другой", callback_data='task_other'))
    
    buttons.append(control_buttons)
    return InlineKeyboardMarkup(buttons)

def get_task_approval_keyboard(task_id):
    """Клавиатура одобрения/отклонения задания"""
    keyboard = [
        [InlineKeyboardButton("✅ Одобрить", callback_data=f'approve_task|{task_id}')],
        [InlineKeyboardButton("❌ Отклонить", callback_data=f'decline_task|{task_id}')]
    ]
    return InlineKeyboardMarkup(keyboard) 
import os
import random
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes
from telegram.error import BadRequest
from config import ADMIN_IDS, SCREENSHOTS_DIR, logger
from database import db
from keyboards import (
    get_participate_keyboard, get_back_inline_keyboard, get_task_control_keyboard,
    create_task_keyboard_with_chats
)
from utils import (
    format_task_panel, format_task_text, make_chat_url
)

async def show_participate_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показать меню выбора типа задания"""
    if update.callback_query:
        query = update.callback_query
        await query.answer()
        target = query.message
        await target.reply_text(
            "Выберите тип задания:",
            reply_markup=get_participate_keyboard()
        )
    else:
        # Удаляем сообщение пользователя "Задания"
        await update.message.delete()
        
        chat_id = update.effective_chat.id
        await context.bot.send_message(
            chat_id=chat_id,
            text="Выберите тип задания:",
            reply_markup=get_participate_keyboard()
        )

async def handle_task_meme(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик задания с мемом"""
    query = update.callback_query
    await query.answer()
    
    # Удаляем меню выбора
    try:
        await query.message.delete()
    except BadRequest:
        pass

    # Получаем случайный шаблон мема
    meme_data = db.get_random_meme()
    if not meme_data:
        await query.message.reply_text("Шаблонов мемов пока нет.")
        return
    
    tpl_id, file_path = meme_data

    # Формируем панель с личным промокодом
    user_stats = db.get_user_stats(query.from_user.id)
    if not user_stats:
        await query.message.reply_text("Ошибка получения данных пользователя.")
        return
    
    panel = format_task_panel(user_stats['promo_code'])

    # Регистрируем задачу в БД
    task_id = db.create_task(query.from_user.id, 'meme', panel)

    # Отправляем сам мем
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

    # Получаем случайные чаты
    chats = db.get_random_chats(limit=5)
    if not chats:
        await query.message.reply_text("Нет доступных чатов.")
        return

    # Создаем клавиатуру с чатами и кнопками управления
    keyboard = create_task_keyboard_with_chats(chats, include_other=True, task_type='meme')
    
    # Отправляем сообщение с кнопками
    list_msg = await context.bot.send_message(
        chat_id=query.message.chat.id,
        text="Список чатов, куда можешь отправить этот мем:",
        reply_markup=keyboard
    )
    context.user_data['last_task_msg_id'] = list_msg.message_id

async def handle_task_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик задания с текстом"""
    query = update.callback_query
    await query.answer()
    
    # Удаляем меню выбора
    try:
        await query.message.delete()
    except BadRequest:
        pass

    # Получаем случайный шаблон текста
    text_data = db.get_random_text()
    if not text_data:
        await query.message.reply_text("Шаблонов текста пока нет.")
        return
    
    tpl_id, txt = text_data

    # Регистрируем задачу в БД
    task_id = db.create_task(query.from_user.id, 'text', txt)

    # Получаем промокод пользователя
    user_stats = db.get_user_stats(query.from_user.id)
    if not user_stats:
        await query.message.reply_text("Ошибка получения данных пользователя.")
        return

    # Формируем новый текст задания
    combined = format_task_text(txt, user_stats['promo_code'])
    
    content_msg = await query.message.reply_text(
        combined,
        parse_mode=ParseMode.HTML
    )
    context.user_data['last_task_content_msg_id'] = content_msg.message_id

    # Получаем случайные чаты
    chats = db.get_random_chats(limit=5)
    if not chats:
        await query.message.reply_text("Нет доступных чатов.")
        return

    # Создаем клавиатуру с чатами и кнопками управления
    keyboard = create_task_keyboard_with_chats(chats, include_other=True, task_type='text')

    # Отправляем сообщение с кнопками
    list_msg = await context.bot.send_message(
        chat_id=query.message.chat.id,
        text="Отправь ⬆️⬆️⬆️ текст в любой из чатов ниже:",
        reply_markup=keyboard
    )
    context.user_data['last_task_msg_id'] = list_msg.message_id

async def handle_task_other_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик запроса другого текстового задания"""
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
    
    # Получаем случайный шаблон текста
    text_data = db.get_random_text()
    if not text_data:
        await query.message.reply_text("Шаблонов текста пока нет.")
        return
    
    tpl_id, txt = text_data

    # Получаем промокод пользователя
    user_stats = db.get_user_stats(query.from_user.id)
    if not user_stats:
        await query.message.reply_text("Ошибка получения данных пользователя.")
        return

    # Формируем новый текст задания
    combined = format_task_text(txt, user_stats['promo_code'])
    
    content_msg = await query.message.reply_text(
        combined,
        parse_mode=ParseMode.HTML
    )
    context.user_data['last_task_content_msg_id'] = content_msg.message_id

    # Получаем случайные чаты
    chats = db.get_random_chats(limit=5)
    if not chats:
        await query.message.reply_text("Нет доступных чатов.")
        return

    # Создаем клавиатуру с чатами и кнопками управления
    keyboard = create_task_keyboard_with_chats(chats, include_other=True, task_type='text')

    # Отправляем сообщение с кнопками
    list_msg = await context.bot.send_message(
        chat_id=query.message.chat.id,
        text="Отправь ⬆️⬆️⬆️ текст в любой из чатов ниже:",
        reply_markup=keyboard
    )
    context.user_data['last_task_msg_id'] = list_msg.message_id

async def handle_task_other_meme(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик запроса другого мема"""
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat.id

    # Удаляем предыдущие сообщения с мемом и кнопками
    for key in ('last_meme_msg_id', 'last_task_msg_id'):
        msg_id = context.user_data.pop(key, None)
        if msg_id:
            try:
                await context.bot.delete_message(chat_id=chat_id, message_id=msg_id)
            except:
                pass

    # Получаем случайный шаблон мема
    meme_data = db.get_random_meme()
    if not meme_data:
        await query.message.reply_text("Шаблонов мемов пока нет.")
        return
    
    tpl_id, file_path = meme_data

    # Формируем панель с личным промокодом
    user_stats = db.get_user_stats(query.from_user.id)
    if not user_stats:
        await query.message.reply_text("Ошибка получения данных пользователя.")
        return
    
    panel = format_task_panel(user_stats['promo_code'])

    # Отправляем мем с панелью
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

    # Получаем случайные чаты
    chats = db.get_random_chats(limit=5)
    if not chats:
        await query.message.reply_text("Нет доступных чатов.")
        return

    # Создаем клавиатуру с чатами и кнопками управления
    keyboard = create_task_keyboard_with_chats(chats, include_other=True, task_type='meme')
    
    list_msg = await context.bot.send_message(
        chat_id=chat_id,
        text="Ниже список чатов, куда можешь отправить ⬆️ этот ⬆️ мем:",
        reply_markup=keyboard
    )
    context.user_data['last_task_msg_id'] = list_msg.message_id

async def handle_task_repost(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик задания репоста"""
    query = update.callback_query
    await query.message.delete()
    
    txt = "Пожалуйста, сделайте репост нашего канала @ambsharing в одном из чатов ниже:"
    task_id = db.create_task(query.from_user.id, 'repost', txt)
    
    chats = db.get_random_chats()
    if not chats:
        await query.message.reply_text("Нет доступных чатов.")
        return
    
    text = txt + "\n\n" + "\n".join(chats)
    await query.message.reply_text(
        text, 
        reply_markup=get_task_control_keyboard()
    )

async def handle_task_back(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик кнопки 'Назад' в заданиях"""
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat.id
    await query.message.delete()

    # Удаляем предыдущее сообщение — либо мем, либо текст
    for key in ('last_task_msg_id', 'last_meme_msg_id', 'last_task_content_msg_id'):
        msg_id = context.user_data.pop(key, None)
        if msg_id:
            try:
                await context.bot.delete_message(chat_id=chat_id, message_id=msg_id)
            except:
                pass
    
    # Отменяем задание и уменьшаем счетчик
    user_id = query.from_user.id
    db.cancel_task(user_id)

async def handle_task_done(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик завершения задания"""
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat.id

    # Отправляем пользователю запрос на скриншот
    context.user_data['awaiting_screenshot'] = True
    prompt = await context.bot.send_message(
        chat_id=chat_id,
        text="📸 <b>Пришлите скриншот выполнения задания</b>",
        parse_mode=ParseMode.HTML
    )
    context.user_data['screenshot_prompt_id'] = prompt.message_id

    # Удаляем старые сообщения с мемом/текстом и кнопками
    for key in ('last_task_msg_id', 'last_meme_msg_id', 'last_task_content_msg_id'):
        msg_id = context.user_data.pop(key, None)
        if msg_id:
            try:
                await context.bot.delete_message(chat_id=chat_id, message_id=msg_id)
            except:
                pass

async def handle_screenshot(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик скриншота"""
    # Обрабатываем скриншоты только если пользователь был запрошен
    if not context.user_data.get('awaiting_screenshot'):
        return
    
    # Очищаем флаг, чтобы обрабатывалось только первое фото
    context.user_data['awaiting_screenshot'] = False
    
    # Удаляем запрос скриншота и фото пользователя
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
    
    # Находим последнее ожидающее задание
    db.cursor.execute(
        "SELECT task_id FROM tasks WHERE user_id = ? AND status = 'pending' ORDER BY created_at DESC LIMIT 1",
        (user.id,)
    )
    row = db.cursor.fetchone()
    if not row:
        await update.message.reply_text("Нет активных заданий.")
        return
    
    task_id = row[0]
    
    # Сохраняем фото
    os.makedirs(SCREENSHOTS_DIR, exist_ok=True)
    path = os.path.join(SCREENSHOTS_DIR, f"{task_id}.jpg")
    await photo_file.download_to_drive(path)
    
    # Обновляем задание
    db.update_screenshot_path(task_id, path)
    
    # Подтверждаем получение пользователю
    await update.message.reply_text(
        "*🔥GOOD! Следи за кол-во пришедших рефералов в профиле!*\n\n"
        "_🤨Не хватает на купон?!_\n"
        "*🗣️Выполни еще заданий или пригласи друга!*",
        parse_mode=ParseMode.MARKDOWN
    )
    
    # Уведомляем админов о новой заявке
    for admin_id in ADMIN_IDS:
        try:
            with open(path, 'rb') as photo:
                caption = (
                    f"📥 <b>Новая заявка от @{user.username or user.id}</b>\n"
                    f"ID задания: {task_id}"
                )
                keyboard = get_task_approval_keyboard(task_id)
                photo_msg = await context.bot.send_photo(
                    chat_id=admin_id,
                    photo=photo,
                    caption=caption,
                    parse_mode=ParseMode.HTML,
                    reply_markup=keyboard
                )
                context.user_data['last_task_photo_msg_id'] = photo_msg.message_id
                context.user_data['last_task_photo_chat_id'] = admin_id
        except Exception as e:
            logger.error(f"Failed to notify admin {admin_id}: {e}")

async def check_tasks_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда проверки заданий для админов"""
    if update.effective_user.id not in ADMIN_IDS:
        return
    
    await update.message.delete()
    
    # Получаем следующее ожидающее задание со скриншотом
    row = db.get_pending_tasks()
    if not row:
        from keyboards import ReplyKeyboardMarkup, KeyboardButton
        await context.bot.send_message(
            chat_id=update.effective_user.id,
            text="Нет новых заявок на проверку.",
            reply_markup=ReplyKeyboardMarkup([[KeyboardButton("Главная")]], resize_keyboard=True)
        )
        return
    
    task_id, task_user_id, screenshot_path, created_at = row
    
    # Получаем username
    db.cursor.execute("SELECT username FROM users WHERE user_id = ?", (task_user_id,))
    uname = db.cursor.fetchone()[0] or str(task_user_id)
    
    # Отправляем скриншот
    if os.path.exists(screenshot_path):
        photo_message = await context.bot.send_photo(
            chat_id=update.effective_user.id, 
            photo=open(screenshot_path, 'rb')
        )
        # Сохраняем ID сообщения с фото для последующего удаления
        context.user_data['last_task_photo_msg_id'] = photo_message.message_id
        context.user_data['last_task_photo_chat_id'] = update.effective_user.id
    
    text = (
        f"Новая заявка от @{uname}\n"
        f"ID: {task_id}\n"
        f"Дата подачи: {created_at}"
    )
    
    keyboard = get_task_approval_keyboard(task_id)
    await context.bot.send_message(
        chat_id=update.effective_user.id,
        text=text,
        reply_markup=keyboard
    ) 
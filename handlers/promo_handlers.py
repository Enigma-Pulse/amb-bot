from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes
from config import ADMIN_IDS, logger
from database import db
from keyboards import (
    get_promo_choose_keyboard, get_promo_offers_keyboard, get_promo_confirm_keyboard,
    get_gift_keyboard, get_back_inline_keyboard
)
from utils import get_gift_text

async def promo_user_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Начало промо-флоу для пользователя"""
    msg = update.message
    user_id = msg.from_user.id
    await msg.delete()
    
    await msg.reply_text(
        "За друзей — промокоды.\n🎁Проверь, хватает ли на подарок",
        reply_markup=get_promo_choose_keyboard()
    )

async def promo_choose_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик выбора промо"""
    query = update.callback_query
    await query.answer()
    
    # Отправляем и сохраняем вводный текст
    intro_msg = await query.message.reply_text(
        "💭<b>ОП ОП ОП</b>\n\n"
        "💥<i>Ты уже пришёл за подарками!</i>\n\n"
        "🎁<b>Вот что можно получить:</b>\n<i>Цена указана справа от названия</i>\n\n"
        "💖 <b>1 преданный реферал = 1💖</b>\n\n"
        "💕 <b>Преданный реферал</b> — тот, кто остался в боте 3 дня после перехода по твоей ссылке.",
        parse_mode=ParseMode.HTML
    )
    context.user_data['promo_intro_msg_id'] = intro_msg.message_id
    
    # Удаляем оригинальный запрос
    await query.message.delete()
    
    # Получаем список офферов
    db.cursor.execute("SELECT offer_id, title, cost FROM promo_offers")
    rows = db.cursor.fetchall()
    
    if not rows:
        await query.message.reply_text(
            "Пока нет доступных промо, зайди позже.", 
            reply_markup=get_back_inline_keyboard()
        )
        return
    
    # Создаем клавиатуру с офферами
    keyboard = get_promo_offers_keyboard(rows)
    
    await query.message.reply_text(
        "🛒<b>ВЫБЕРИ ТОВАР</b>", 
        reply_markup=keyboard, 
        parse_mode=ParseMode.HTML
    )

async def promo_back_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик кнопки 'Назад' в промо"""
    query = update.callback_query
    await query.answer()
    
    # Удаляем вводное сообщение если есть
    intro_id = context.user_data.pop('promo_intro_msg_id', None)
    if intro_id:
        await context.bot.delete_message(chat_id=query.message.chat_id, message_id=intro_id)
    
    # Удаляем текущее сообщение со списком
    await query.message.delete()

async def promo_offer_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик выбора промо-оффера"""
    query = update.callback_query
    await query.answer()
    
    _, oid = query.data.split('|', 1)
    
    # Получаем данные оффера
    db.cursor.execute("SELECT title, cost FROM promo_offers WHERE offer_id = ?", (oid,))
    row = db.cursor.fetchone()
    
    if not row:
        await query.message.reply_text(
            "Ошибка: оффер не найден.", 
            reply_markup=get_back_inline_keyboard()
        )
        return
    
    title, cost = row
    user_id = query.from_user.id
    
    # Подсчитываем доступные преданные рефералы
    user_stats = db.get_user_stats(user_id)
    if not user_stats:
        await query.message.reply_text("Ошибка получения данных пользователя.")
        return
    
    total_loyal = user_stats['loyal_referrals']
    used_loyal = user_stats['used_loyal']
    available = total_loyal - used_loyal
    
    if available < cost:
        # Удаляем список промо и вводные сообщения
        await query.message.delete()
        intro_id = context.user_data.pop('promo_intro_msg_id', None)
        if intro_id:
            await context.bot.delete_message(
                chat_id=query.message.chat_id, 
                message_id=intro_id
            )
        
        # Уведомляем пользователя с мягким сообщением и кнопкой назад
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=(
                "🙈<i>Упс, похоже тебе пока не хватает преданных рефералов</i>\n\n"
                f"➖<b>У тебя сейчас {available}/{cost}</b>\n\n"
                "🗣️<b>Попробуй пригласить ещё</b>"
            ),
            parse_mode=ParseMode.HTML,
            reply_markup=get_back_inline_keyboard()
        )
        return
    
    # Создаем клавиатуру подтверждения
    keyboard = get_promo_confirm_keyboard(oid)
    
    await query.message.delete()
    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text=f"Хочешь получить «{title}» за {cost} преданных?",
        reply_markup=keyboard
    )

async def promo_confirm_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик подтверждения промо"""
    query = update.callback_query
    await query.answer()
    
    _, oid = query.data.split('|', 1)
    
    # Получаем данные оффера
    db.cursor.execute("SELECT title, cost FROM promo_offers WHERE offer_id = ?", (oid,))
    row = db.cursor.fetchone()
    
    if not row:
        await query.message.reply_text(
            "Ошибка: оффер не найден.", 
            reply_markup=get_back_inline_keyboard()
        )
        return
    
    title, cost = row
    user_id = query.from_user.id
    
    # Пересчитываем доступные
    user_stats = db.get_user_stats(user_id)
    if not user_stats:
        await query.message.reply_text("Ошибка получения данных пользователя.")
        return
    
    total_loyal = user_stats['loyal_referrals']
    used_loyal = user_stats['used_loyal']
    available = max(0, total_loyal - used_loyal)  # Защита от отрицательных значений
    
    if available < cost:
        await query.answer("Недостаточно преданных рефералов.", show_alert=True)
        return
    
    # Списываем стоимость с преданных рефералов пользователя
    db.cursor.execute(
        "UPDATE users SET used_loyal = used_loyal + ? WHERE user_id = ?",
        (cost, user_id)
    )
    db.conn.commit()
    
    # Создаем задание на промо
    from datetime import datetime
    now = datetime.now()
    db.cursor.execute(
        "INSERT INTO tasks (user_id, task_type, task_description, created_at) VALUES (?, 'promo', ?, ?)",
        (user_id, f"offer:{oid}", now)
    )
    task_id = db.cursor.lastrowid
    db.conn.commit()

    # Уведомляем всех админов о новой заявке на промо
    for admin_id in ADMIN_IDS:
        from keyboards import InlineKeyboardMarkup, InlineKeyboardButton
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

async def prompt_promo_code(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Запрос ввода промокода"""
    from config import ENTER_CODE
    
    # Удаляем сообщение с кнопкой и просим ввести код
    await update.message.delete()
    
    # Отправляем запрос и сохраняем его message_id для последующего удаления
    prompt = await update.message.reply_text("🔑 Введите промокод, который вам дал друг:")
    context.user_data['promo_prompt_msg_id'] = prompt.message_id
    
    return ENTER_CODE

async def receive_promo_code(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Получение промокода от пользователя"""
    from config import ENTER_CODE
    from telegram.ext import ConversationHandler
    
    code = update.message.text.strip().upper()
    user_id = update.effective_user.id
    
    # Удаляем запрос промокода
    prompt_id = context.user_data.pop('promo_prompt_msg_id', None)
    if prompt_id:
        await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=prompt_id)
    
    # Удаляем сообщение с введенным кодом
    await update.message.delete()

    # Проверяем, что не свой собственный код
    user_stats = db.get_user_stats(user_id)
    if not user_stats:
        await context.bot.send_message(
            chat_id=user_id,
            text="Ошибка получения данных пользователя."
        )
        return ConversationHandler.END
    
    my_code = user_stats['promo_code']
    if code == my_code:
        await context.bot.send_message(
            chat_id=user_id,
            text="❌ Нельзя вводить свой же промокод."
        )
        return ConversationHandler.END

    # Ищем владельца кода
    owner_id = db.get_user_by_promo_code(code)
    if not owner_id:
        await context.bot.send_message(
            user_id, 
            "❌ Промокод не найден. Попробуйте ещё раз."
        )
        return ConversationHandler.END

    # Проверяем, что реферал еще не привязан
    db.cursor.execute("SELECT ref_by FROM users WHERE user_id = ?", (user_id,))
    ref_by = db.cursor.fetchone()[0]
    
    if ref_by is not None:
        await context.bot.send_message(
            user_id, 
            "⚠️ Вы уже привязаны к рефереру."
        )
        return ConversationHandler.END

    # Сохраняем реферера и увеличиваем счетчик
    db.cursor.execute("UPDATE users SET ref_by = ? WHERE user_id = ?", (owner_id, user_id))
    db.cursor.execute("UPDATE users SET referrals_count = referrals_count + 1 WHERE user_id = ?", (owner_id,))
    db.conn.commit()

    # Планируем проверку лояльности через 3 дня
    from handlers.user_handlers import credit_loyal_referral
    context.job_queue.run_once(
        credit_loyal_referral,
        when=3*24*60*60,
        chat_id=owner_id,
        data=user_id
    )
    
    # Отправляем активацию + кнопку «Забрать»
    response_msg = await context.bot.send_message(
        chat_id=user_id,
        text=(
            "✅NICE Ваш промо <b>АКТИВИРОВАН</b>\n\n"
            "🎁<b>ВАМ ДОСТУПЕН ПОДАРОК</b>"
        ),
        parse_mode=ParseMode.HTML,
        reply_markup=get_gift_keyboard()
    )
    
    # Уведомляем владельца кода
    await context.bot.send_message(
        chat_id=owner_id,
        text="✅<b>У тебя +1 новый реферал‼️</b>\n🎉Проверь профиль",
        parse_mode=ParseMode.HTML
    )
    
    return ConversationHandler.END

async def get_gift(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Получение подарка"""
    query = update.callback_query
    await query.answer()
    await query.message.delete()

    # Генерируем или берем статический подарок-код
    gift_code = "QODMSH"  # можно динамически вытаскивать из БД

    # Отправляем детали подарка
    await context.bot.send_message(
        chat_id=query.from_user.id,
        text=get_gift_text(gift_code),
        parse_mode=ParseMode.HTML
    ) 
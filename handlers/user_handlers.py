from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes
from config import CHANNEL_ID, RULES_TEXT, WELCOME_IMAGE_PATH, REMINDER_IMAGE_PATH, logger
from database import db
from keyboards import (
    get_main_reply_keyboard, get_back_inline_keyboard, get_subscription_check_keyboard,
    get_rules_accept_keyboard, get_rules_final_accept_keyboard, get_main_inline_keyboard
)
from utils import (
    is_user_subscribed, format_profile_text, get_welcome_caption, get_main_screen_text,
    get_subscription_text, get_reminder_text, parse_start_parameter, ensure_directories,
    clear_subscription_cache, force_check_subscription
)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /start"""
    # Определяем объект сообщения (поддерживает команду или callback)
    if update.callback_query:
        message = update.callback_query.message
    else:
        message = update.message
    
    user = update.effective_user
    
    # Проверяем подписку на канал
    if not await is_user_subscribed(context.bot, user.id):
        await message.reply_text(
            get_subscription_text(),
            reply_markup=get_subscription_check_keyboard(),
            parse_mode='HTML'
        )
        return

    # Парсим параметр start для реферальной системы
    ref_by = None
    if update.message and update.message.text:
        ref_by = parse_start_parameter(update.message.text)
    
    # Получаем или создаем пользователя
    promo_code = db.get_or_create_user(
        user_id=user.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name,
        ref_by=ref_by
    )
    
    # Планируем напоминание через 23 минуты
    context.job_queue.run_once(
        send_referral_reminder,
        when=23 * 60,
        chat_id=update.effective_chat.id
    )
    
    # Планируем проверку лояльности через 3 дня если есть реферер
    if ref_by is not None and ref_by != user.id:
        context.job_queue.run_once(
            credit_loyal_referral,
            when=3*24*60*60,
            chat_id=ref_by,
            data=user.id
        )
        await notify_simple_referral(context, ref_by)

    # Отправляем приветственное изображение
    reply_keyboard = get_main_reply_keyboard(is_admin=user.id in [6798547914])  # TODO: вынести в конфиг
    
    await message.reply_photo(
        photo=open(WELCOME_IMAGE_PATH, 'rb'),
        caption=get_welcome_caption(),
        parse_mode=ParseMode.HTML,
        reply_markup=reply_keyboard
    )
    
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="Прочитай наши правила",
        reply_markup=get_rules_accept_keyboard()
    )

async def check_subscription_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик проверки подписки - МГНОВЕННАЯ ПРОВЕРКА"""
    query = update.callback_query
    user_id = query.from_user.id
    
    # Мгновенная проверка подписки
    if await force_check_subscription(context.bot, user_id):
        await query.message.delete()
        # Пользователь подписан, перезапускаем onboarding
        await start(update, context)
    else:
        await query.answer("Ты еще не подписан на канал.", show_alert=True)

async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик профиля пользователя"""
    user = update.effective_user
    user_stats = db.get_user_stats(user.id)
    
    if not user_stats:
        await update.message.reply_text("Профиль не найден.")
        return
    
    profile_text = format_profile_text(user_stats, user.id, user.username)
    
    if update.callback_query:
        await update.callback_query.edit_message_text(
            profile_text, 
            parse_mode=ParseMode.HTML
        )
    else:
        await update.message.delete()
        await update.message.reply_text(
            profile_text,
            parse_mode=ParseMode.HTML,
            reply_markup=get_back_inline_keyboard()
        )

async def rules_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик правил"""
    await update.message.delete()
    await update.message.reply_text(
        RULES_TEXT,
        parse_mode=ParseMode.HTML,
        reply_markup=get_back_inline_keyboard()
    )

async def show_rules_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик показа правил после нажатия '💡Прочитал'"""
    query = update.callback_query
    
    # Удаляем сообщение с кнопкой "💡Прочитал"
    try:
        await query.message.delete()
    except Exception:
        pass
    
    # Отправляем правила с кнопкой "✅Прочитал"
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=RULES_TEXT,
        parse_mode=ParseMode.HTML,
        reply_markup=get_rules_final_accept_keyboard()
    )

async def support_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик поддержки"""
    await update.message.delete()
    await update.message.reply_text(
        "По вопросам: @amb_managers",
        reply_markup=get_back_inline_keyboard()
    )

async def main_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик кнопки 'Главная'"""
    await update.message.delete()
    await send_main_reply_keyboard(update, context)

async def send_main_reply_keyboard(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отправка главной reply клавиатуры"""
    # Удаляем предыдущее сообщение главного экрана если есть
    prev = context.user_data.get('last_main_msg')
    if prev:
        try:
            await context.bot.delete_message(chat_id=prev['chat_id'], message_id=prev['message_id'])
        except:
            pass
    context.user_data['last_main_msg'] = None
    
    user_id = update.effective_user.id
    reply_keyboard = get_main_reply_keyboard(is_admin=user_id in [6798547914])  # TODO: вынести в конфиг
    
    # Определяем куда отправлять
    if hasattr(update, "callback_query") and update.callback_query:
        target = update.callback_query.message
    else:
        target = update.message
    
    main_msg = await target.reply_text(
        get_main_screen_text(),
        parse_mode=ParseMode.HTML,
        reply_markup=reply_keyboard
    )
    
    # Сохраняем сообщение главного экрана для последующего удаления
    context.user_data['last_main_msg'] = {
        'chat_id': main_msg.chat_id,
        'message_id': main_msg.message_id
    }

# Вспомогательные функции
async def notify_simple_referral(context: ContextTypes.DEFAULT_TYPE, user_id: int) -> None:
    """Уведомление о новом реферале"""
    await context.bot.send_message(
        chat_id=user_id,
        text="🔔<b>+1 реферал у тебя появился</b>\n😏Станет ли он преданным⁉️",
        parse_mode=ParseMode.HTML
    )

async def credit_loyal_referral(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Начисление лояльного реферала"""
    job = context.job
    referrer_id = job.chat_id
    referral_id = job.data
    
    logger.info(f"Checking loyalty for referrer {referrer_id}, referral {referral_id}")
    
    try:
        # Проверяем, существует ли реферал в базе данных
        db.cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (referral_id,))
        if not db.cursor.fetchone():
            logger.warning(f"Referral {referral_id} not found in database")
            return
        
        # Проверяем, не был ли уже начислен преданный реферал
        if db.is_loyal_referral_credited(referrer_id, referral_id):
            logger.info(f"Loyal referral already credited for {referrer_id} <- {referral_id}")
            return
        
        # Проверяем подписку реферала
        is_subscribed = await is_user_subscribed(context.bot, referral_id)
        logger.info(f"Referral {referral_id} subscription status: {is_subscribed}")
        
        if is_subscribed:
            # Получаем текущие данные реферера
            db.cursor.execute("""
                SELECT loyal_referrals, used_loyal FROM users WHERE user_id = ?
            """, (referrer_id,))
            result = db.cursor.fetchone()
            
            if result:
                current_loyal, used_loyal = result
                current_loyal = current_loyal or 0
                used_loyal = used_loyal or 0
                
                # Увеличиваем счетчик преданных рефералов
                new_loyal_referrals = current_loyal + 1
                
                # Обновляем счетчик
                db.cursor.execute(
                    "UPDATE users SET loyal_referrals = ? WHERE user_id = ?",
                    (new_loyal_referrals, referrer_id)
                )
                
                # Отмечаем, что преданный реферал был начислен
                db.mark_loyal_referral_credited(referrer_id, referral_id)
                
                logger.info(f"Credited loyal referral for {referrer_id}: {current_loyal} -> {new_loyal_referrals} (used: {used_loyal})")
                
                await context.bot.send_message(
                    chat_id=referrer_id,
                    text=(
                        "🎉<b>ТВОЙ РЕФЕРАЛ СТАЛ ПРЕДАННЫМ💖</b>\n"
                        "<b>➖Посмотри в профиле, хватает ли тебе на промо⁉️</b>"
                    ),
                    parse_mode=ParseMode.HTML
                )
        else:
            logger.info(f"Referral {referral_id} is not subscribed, no credit given")
            
    except Exception as e:
        logger.error(f"Error crediting loyal referral for {referrer_id}/{referral_id}: {e}")

async def send_referral_reminder(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отправка напоминания о реферале"""
    job = context.job
    user_id = job.chat_id
    
    # Отправляем картинку и маркетинговый текст
    with open(REMINDER_IMAGE_PATH, "rb") as photo:
        await context.bot.send_photo(
            chat_id=user_id,
            photo=photo,
            caption=get_reminder_text(),
            parse_mode=ParseMode.HTML
        )

async def get_my_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Получение ID пользователя"""
    user = update.effective_user
    await update.message.reply_text(
        f"👤 <b>Ваш ID:</b> <code>{user.id}</code>\n"
        f"📝 <b>Username:</b> @{user.username or 'нет'}\n"
        f"👨‍💼 <b>Имя:</b> {user.first_name or 'нет'}",
        parse_mode=ParseMode.HTML
    )

async def refresh_subscription(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Принудительное обновление проверки подписки - МГНОВЕННАЯ"""
    user = update.effective_user
    
    # Мгновенная проверка подписки
    is_subscribed = await force_check_subscription(context.bot, user.id)
    
    if is_subscribed:
        await update.message.reply_text(
            "✅ <b>Подписка подтверждена!</b>\n\n"
            "Теперь вы можете использовать бота. Напишите /start для продолжения.",
            parse_mode=ParseMode.HTML
        )
    else:
        await update.message.reply_text(
            "❌ <b>Подписка не найдена</b>\n\n"
            "Убедитесь, что вы подписаны на канал и попробуйте снова.",
            parse_mode=ParseMode.HTML
        )

async def check_loyalty_manual(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Ручная проверка преданности рефералов (только для админов)"""
    from config import ADMIN_IDS
    
    if update.effective_user.id not in ADMIN_IDS:
        await update.message.reply_text("❌ Команда доступна только администраторам.")
        return
    
    await update.message.delete()
    
    # Находим всех рефералов старше 3 дней
    from datetime import datetime, timedelta
    three_days_ago = datetime.now() - timedelta(days=3)
    
    db.cursor.execute("""
        SELECT u.user_id, u.username, u.ref_by, u.joined_date
        FROM users u
        WHERE u.ref_by IS NOT NULL 
        AND u.joined_date < ?
        ORDER BY u.joined_date DESC
    """, (three_days_ago.isoformat(),))
    
    old_referrals = db.cursor.fetchall()
    
    if not old_referrals:
        await update.message.reply_text("📊 Нет рефералов старше 3 дней для проверки.")
        return
    
    await update.message.reply_text(f"🔍 Найдено {len(old_referrals)} рефералов старше 3 дней. Начинаю проверку...")
    
    processed = 0
    credited = 0
    already_credited = 0
    
    # Создаем словарь для подсчета реальных преданных рефералов
    real_loyal_counts = {}
    
    for user_id, username, ref_by, joined_date in old_referrals:
        try:
            # Проверяем подписку
            if await is_user_subscribed(context.bot, user_id):
                # Увеличиваем счетчик реальных преданных рефералов
                if ref_by not in real_loyal_counts:
                    real_loyal_counts[ref_by] = 0
                real_loyal_counts[ref_by] += 1
                
                # Отмечаем в таблице отслеживания
                if not db.is_loyal_referral_credited(ref_by, user_id):
                    db.mark_loyal_referral_credited(ref_by, user_id)
                    credited += 1
            
            processed += 1
            
        except Exception as e:
            logger.error(f"Error processing referral {user_id}: {e}")
    
    # Теперь обновляем счетчики с учетом потраченных
    updated_users = 0
    for ref_by, real_loyal_count in real_loyal_counts.items():
        try:
            # Получаем текущие данные пользователя
            db.cursor.execute("""
                SELECT loyal_referrals, used_loyal FROM users WHERE user_id = ?
            """, (ref_by,))
            result = db.cursor.fetchone()
            
            if result:
                current_loyal, used_loyal = result
                used_loyal = used_loyal or 0
                
                # Устанавливаем правильный баланс: реальные преданные - потраченные
                new_loyal_referrals = max(0, real_loyal_count - used_loyal)
                
                # Обновляем только если значение изменилось
                if new_loyal_referrals != current_loyal:
                    db.cursor.execute("""
                        UPDATE users SET loyal_referrals = ? WHERE user_id = ?
                    """, (new_loyal_referrals, ref_by))
                    updated_users += 1
                    logger.info(f"Updated loyal referrals for {ref_by}: {current_loyal} -> {new_loyal_referrals} (real: {real_loyal_count}, used: {used_loyal})")
                
        except Exception as e:
            logger.error(f"Error updating user {ref_by}: {e}")
    
    # Обнуляем счетчики для тех, у кого нет реальных преданных рефералов
    db.cursor.execute("""
        SELECT user_id, loyal_referrals, used_loyal 
        FROM users 
        WHERE loyal_referrals > 0 AND user_id NOT IN ({})
    """.format(','.join('?' * len(real_loyal_counts))), list(real_loyal_counts.keys()) if real_loyal_counts else [0])
    
    users_to_reset = db.cursor.fetchall()
    reset_users = 0
    
    for user_id, current_loyal, used_loyal in users_to_reset:
        try:
            used_loyal = used_loyal or 0
            new_loyal_referrals = max(0, 0 - used_loyal)  # 0 реальных - потраченные
            
            if new_loyal_referrals != current_loyal:
                db.cursor.execute("""
                    UPDATE users SET loyal_referrals = ? WHERE user_id = ?
                """, (new_loyal_referrals, user_id))
                reset_users += 1
                logger.info(f"Reset loyal referrals for {user_id}: {current_loyal} -> {new_loyal_referrals}")
        except Exception as e:
            logger.error(f"Error resetting user {user_id}: {e}")
    
    db.conn.commit()
    
    await update.message.reply_text(
        f"✅ Проверка завершена!\n"
        f"📊 Обработано рефералов: {processed}\n"
        f"💖 Начислено новых преданных: {credited}\n"
        f"🔄 Обновлено пользователей: {updated_users}\n"
        f"🔄 Сброшено пользователей: {reset_users}\n"
        f"📈 Реальных преданных рефералов: {sum(real_loyal_counts.values())}"
    )

async def general_back_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик общей кнопки 'Назад'"""
    query = update.callback_query
    await query.answer()
    
    # Просто удаляем сообщение с кнопкой "Назад"
    try:
        await query.message.delete()
    except Exception:
        pass

async def accept_rules_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик финального принятия правил"""
    query = update.callback_query
    user = query.from_user
    
    # Удаляем сообщение с правилами
    try:
        await query.message.delete()
    except Exception:
        pass
    
    # Парсим параметр start для реферальной системы (если есть)
    ref_by = None
    if hasattr(update, 'message') and update.message and update.message.text:
        ref_by = parse_start_parameter(update.message.text)
    
    # Получаем или создаем пользователя
    promo_code = db.get_or_create_user(
        user_id=user.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name,
        ref_by=ref_by
    )
    
    # Планируем напоминание через 23 минуты
    context.job_queue.run_once(
        send_referral_reminder,
        when=23 * 60,
        chat_id=update.effective_chat.id
    )
    
    # Планируем проверку лояльности через 3 дня если есть реферер
    if ref_by is not None and ref_by != user.id:
        context.job_queue.run_once(
            credit_loyal_referral,
            when=3*24*60*60,
            chat_id=ref_by,
            data=user.id
        )
        await notify_simple_referral(context, ref_by)

    # Отправляем сообщение о промокоде
    promo_text = (
        "🛑Стой-стой-стой..\n"
        "👉У тебя есть <b>ПРОМОКОД</b>⁉️\n\n"
        "<b>Введи его и получи подарок!</b>\n\n"
        "⬇️ Жми на кнопку \"✅Ввести ПРОМО\" ⬇️\n"
    )
    
    reply_keyboard = get_main_reply_keyboard(is_admin=user.id in [6798547914])  # TODO: вынести в конфиг
    
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=promo_text,
        parse_mode=ParseMode.HTML,
        reply_markup=reply_keyboard
    ) 
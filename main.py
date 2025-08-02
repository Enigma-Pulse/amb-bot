#!/usr/bin/env python3
"""
AMB Promo Bot - Главный файл
Модульная архитектура для Telegram бота
"""

import logging
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ConversationHandler,
    ContextTypes
)

# Импорты конфигурации
from config import TOKEN, ADMIN_IDS, ENTER_CODE, logger

# Импорты базы данных
from database import db

# Импорты утилит
from utils import ensure_directories, reset_broadcast_state

# Импорты клавиатур
from keyboards import get_back_inline_keyboard

# Импорты обработчиков
from handlers.user_handlers import (
    start, check_subscription_handler, profile, rules_handler, 
    support_handler, main_button_handler, send_main_reply_keyboard, get_my_id,
    accept_rules_handler, refresh_subscription, show_rules_handler, general_back_handler,
    check_loyalty_manual
)

from handlers.admin_handlers import (
    admin_panel, content_command, content_add_meme_handler, content_delete_meme_handler,
    content_list_chats_handler, content_add_chat_handler, content_delete_chat_handler,
    content_add_text_handler, content_list_texts_handler, promo_panel, promo_add_offer_handler,
    promo_delete_offer_handler, promo_list_offers_handler, stats_command, 
    send_users_file_handler, broadcast_panel, handle_admin_broadcast_message,
    handle_admin_input, clear_chat, debug_subscription_command, clear_cache_command,
    check_db_status
)

from handlers.task_handlers import (
    show_participate_menu, handle_task_meme, handle_task_text, handle_task_other_text,
    handle_task_other_meme, handle_task_repost, handle_task_back, handle_task_done,
    handle_screenshot, check_tasks_command
)

from handlers.promo_handlers import (
    promo_user_start, promo_choose_handler, promo_back_handler, promo_offer_handler,
    promo_confirm_handler, prompt_promo_code, receive_promo_code, get_gift
)

async def handle_task_approval(update: Update, context: ContextTypes.DEFAULT_TYPE, action: str) -> None:
    """Обработчик одобрения/отклонения заданий"""
    query = update.callback_query
    await query.answer()
    
    _, task_id = query.data.split('|', 1)
    task_id = int(task_id)
    
    # Получаем данные задания
    db.cursor.execute("SELECT user_id, task_type FROM tasks WHERE task_id = ?", (task_id,))
    row = db.cursor.fetchone()
    if not row:
        await query.message.edit_text("Задание не найдено.")
        return
    
    user_id, task_type = row
    
    if action == 'approve':
        if task_type == 'promo':
            # Запрашиваем код купона у админа
            context.user_data['task_stage'] = 'await_promo_code'
            context.user_data['task_id'] = task_id
            context.user_data['task_user_id'] = user_id
            await query.message.edit_text(
                "Введите код купона для промо:",
                reply_markup=get_back_inline_keyboard()
            )
            return
        
        # Обычное одобрение для других заданий
        db.approve_task(task_id, user_id)
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
    else:  # decline
        db.decline_task(task_id, user_id)
        await context.bot.send_message(
            chat_id=user_id,
            text=(
                "*😕АЙ БРАТ ОБИЖАЕШЬ*\n\n"
                "➖_Задание не одобрил админ\nВозможно, ты не выполнил условия или не приложил скриншот._\n\n"
                "☑️*Попробуй еще раз!*"
            ),
            parse_mode=ParseMode.MARKDOWN
        )
    
    # Удаляем сообщение админа и фото
    photo_msg_id = context.user_data.pop('last_task_photo_msg_id', None)
    photo_chat_id = context.user_data.pop('last_task_photo_chat_id', None)
    if photo_msg_id and photo_chat_id:
        try:
            await context.bot.delete_message(chat_id=photo_chat_id, message_id=photo_msg_id)
        except:
            pass
    await query.message.delete()

def main() -> None:
    """Главная функция запуска бота"""
    # Создаем необходимые директории
    ensure_directories()
    
    # Создаем приложение
    application = ApplicationBuilder().token(TOKEN).build()
    
    # ===== РЕГИСТРАЦИЯ ОБРАБОТЧИКОВ КОМАНД =====
    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('profile', profile))
    application.add_handler(CommandHandler('clear', clear_chat))
    application.add_handler(CommandHandler('debug_sub', debug_subscription_command))
    application.add_handler(CommandHandler('clear_cache', clear_cache_command))
    application.add_handler(CommandHandler('myid', get_my_id))
    application.add_handler(CommandHandler('refresh', refresh_subscription))
    application.add_handler(CommandHandler('check_loyalty', check_loyalty_manual))
    application.add_handler(CommandHandler('db_status', check_db_status))
    
    # ===== РЕГИСТРАЦИЯ CALLBACK ОБРАБОТЧИКОВ =====
    
    # Основные callback обработчики
    application.add_handler(
        CallbackQueryHandler(check_subscription_handler, pattern='^check_subscription$')
    )
    application.add_handler(
        CallbackQueryHandler(send_users_file_handler, pattern='^get_users_file$')
    )
    
    # Промо callback обработчики
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
        CallbackQueryHandler(get_gift, pattern='^get_gift$')
    )
    
    # Задания callback обработчики
    application.add_handler(
        CallbackQueryHandler(show_participate_menu, pattern='^participate$')
    )
    application.add_handler(
        CallbackQueryHandler(handle_task_meme, pattern='^task_meme$')
    )
    application.add_handler(
        CallbackQueryHandler(handle_task_text, pattern='^task_text$')
    )
    application.add_handler(
        CallbackQueryHandler(handle_task_other_text, pattern='^task_other_text$')
    )
    application.add_handler(
        CallbackQueryHandler(handle_task_other_meme, pattern='^task_other_meme$')
    )
    application.add_handler(
        CallbackQueryHandler(handle_task_repost, pattern='^task_repost$')
    )
    application.add_handler(
        CallbackQueryHandler(handle_task_back, pattern='^task_back$')
    )
    application.add_handler(
        CallbackQueryHandler(handle_task_done, pattern='^task_done$')
    )
    
    # Админские callback обработчики
    application.add_handler(
        CallbackQueryHandler(lambda u, c: broadcast_panel(u, c), pattern='^admin_broadcast$')
    )
    application.add_handler(
        CallbackQueryHandler(lambda u, c: reset_broadcast_state(c), pattern='^bc_cancel$')
    )
    application.add_handler(
        CallbackQueryHandler(lambda u, c: None, pattern='^bc_attach_photo$')  # TODO: implement
    )
    application.add_handler(
        CallbackQueryHandler(lambda u, c: None, pattern='^bc_send_confirm$')  # TODO: implement
    )
    application.add_handler(
        CallbackQueryHandler(lambda u, c: None, pattern='^bc_execute$')  # TODO: implement
    )
    
    # Обработчики одобрения/отклонения заданий
    application.add_handler(
        CallbackQueryHandler(lambda u, c: handle_task_approval(u, c, 'approve'), pattern=r'^approve_task\|\d+$')
    )
    application.add_handler(
        CallbackQueryHandler(lambda u, c: handle_task_approval(u, c, 'decline'), pattern=r'^decline_task\|\d+$')
    )
    
    # Обработчики профиля и правил
    application.add_handler(
        CallbackQueryHandler(profile, pattern='^profile$')
    )
    application.add_handler(
        CallbackQueryHandler(rules_handler, pattern='^rules$')
    )
    application.add_handler(
        CallbackQueryHandler(support_handler, pattern='^support$')
    )
    application.add_handler(
        CallbackQueryHandler(show_rules_handler, pattern='^start_accept_rules$')
    )
    application.add_handler(
        CallbackQueryHandler(accept_rules_handler, pattern='^final_accept_rules$')
    )
    application.add_handler(
        CallbackQueryHandler(general_back_handler, pattern='^general_back$')
    )
    
    # ===== РЕГИСТРАЦИЯ MESSAGE ОБРАБОТЧИКОВ =====
    
    # Пользовательские кнопки
    application.add_handler(
        MessageHandler(filters.Regex('^👤 Профиль$'), profile)
    )
    application.add_handler(
        MessageHandler(filters.Regex('^ℹ️ Правила$'), rules_handler)
    )
    application.add_handler(
        MessageHandler(filters.Regex('^🛠 Поддержка$'), support_handler)
    )
    application.add_handler(
        MessageHandler(filters.Regex('^Главная$'), main_button_handler)
    )
    application.add_handler(
        MessageHandler(filters.Regex('^Задания$'), show_participate_menu)
    )
    application.add_handler(
        MessageHandler(filters.Regex('^🔥Получить ПРОМО$'), promo_user_start)
    )
    
    # Админские кнопки
    application.add_handler(
        MessageHandler(filters.Regex('^Админ$') & filters.User(ADMIN_IDS), admin_panel)
    )
    application.add_handler(
        MessageHandler(filters.Regex('^Контент$') & filters.User(ADMIN_IDS), content_command)
    )
    application.add_handler(
        MessageHandler(filters.Regex('^Промо$') & filters.User(ADMIN_IDS), promo_panel)
    )
    application.add_handler(
        MessageHandler(filters.Regex('^Статистика$') & filters.User(ADMIN_IDS), stats_command)
    )
    application.add_handler(
        MessageHandler(filters.Regex('^Рассылка$') & filters.User(ADMIN_IDS), broadcast_panel)
    )
    
    # Админские подменю контента
    application.add_handler(
        MessageHandler(filters.Regex('^📥 Добавить мем$') & filters.User(ADMIN_IDS), content_add_meme_handler)
    )
    application.add_handler(
        MessageHandler(filters.Regex('^🗑 Удалить мем$') & filters.User(ADMIN_IDS), content_delete_meme_handler)
    )
    application.add_handler(
        MessageHandler(filters.Regex('^📋 Список чатов$') & filters.User(ADMIN_IDS), content_list_chats_handler)
    )
    application.add_handler(
        MessageHandler(filters.Regex('^➕ Добавить чат$') & filters.User(ADMIN_IDS), content_add_chat_handler)
    )
    application.add_handler(
        MessageHandler(filters.Regex('^🗑 Удалить чат$') & filters.User(ADMIN_IDS), content_delete_chat_handler)
    )
    application.add_handler(
        MessageHandler(filters.Regex('^✍️ Добавить текст$') & filters.User(ADMIN_IDS), content_add_text_handler)
    )
    application.add_handler(
        MessageHandler(filters.Regex('^🧾 Список текстов$') & filters.User(ADMIN_IDS), content_list_texts_handler)
    )
    application.add_handler(
        MessageHandler(filters.Regex('^🔙 Назад$') & filters.User(ADMIN_IDS), admin_panel)
    )
    
    # Админские подменю промо
    application.add_handler(
        MessageHandler(filters.Regex('^📥 Добавить оффер$') & filters.User(ADMIN_IDS), promo_add_offer_handler)
    )
    application.add_handler(
        MessageHandler(filters.Regex('^🗑 Удалить оффер$') & filters.User(ADMIN_IDS), promo_delete_offer_handler)
    )
    application.add_handler(
        MessageHandler(filters.Regex('^📋 Список офферов$') & filters.User(ADMIN_IDS), promo_list_offers_handler)
    )
    
    # ===== CONVERSATION HANDLER ДЛЯ ПРОМОКОДОВ =====
    promo_conv = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex('^✅Ввести ПРОМО$'), prompt_promo_code)
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
    
    # ===== ОБРАБОТЧИКИ АДМИНСКОГО ВВОДА =====
    application.add_handler(
        MessageHandler(
            filters.TEXT & filters.User(ADMIN_IDS), 
            handle_admin_broadcast_message
        )
    )
    application.add_handler(
        MessageHandler(
            filters.ALL & filters.User(ADMIN_IDS) & ~filters.Regex('^Админ$') & ~filters.Regex('^Статистика$'),
            handle_admin_input
        ),
        group=1
    )
    
    # ===== ОБРАБОТЧИКИ ФОТО/ДОКУМЕНТОВ =====
    application.add_handler(
        MessageHandler(
            filters.PHOTO | filters.Document.IMAGE,
            handle_screenshot
        )
    )
    
    logger.info("Бот запущен!")
    application.run_polling()

if __name__ == '__main__':
    main() 
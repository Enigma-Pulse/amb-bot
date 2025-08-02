import os
import csv
from datetime import datetime, timedelta
from telegram import Update
from telegram.constants import ParseMode, ChatType
from telegram.ext import ContextTypes
from config import ADMIN_IDS, logger, SCREENSHOTS_DIR, MEMES_DIR
from database import db
from keyboards import (
    get_admin_reply_keyboard, get_content_reply_keyboard, get_promo_reply_keyboard,
    get_back_inline_keyboard, get_task_approval_keyboard, get_users_file_keyboard,
    get_broadcast_keyboard
)
from utils import (
    reset_broadcast_state, get_stats_text, get_date_range, make_chat_url, debug_subscription, clear_subscription_cache,
    BROADCAST_STAGE_TEXT, BROADCAST_STAGE_PHOTO, BROADCAST_STAGE_CONFIRM,
    CONTENT_STAGE_ADD_MEME, CONTENT_STAGE_DELETE_MEME, CONTENT_STAGE_ADD_TEXT,
    CONTENT_STAGE_LIST_TEXTS, CONTENT_STAGE_LIST_CHATS, CONTENT_STAGE_ADD_CHAT,
    CONTENT_STAGE_DELETE_CHAT, PROMO_STAGE_ADD, PROMO_STAGE_DELETE
)

def is_admin(user_id: int) -> bool:
    """Проверка является ли пользователь администратором"""
    return user_id in ADMIN_IDS

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Панель администратора"""
    if not is_admin(update.effective_user.id):
        return
    
    # Очищаем любые ожидающие состояния админских флоу
    for key in ['promo_stage', 'content_stage', 'broadcast_stage', 'task_stage']:
        context.user_data.pop(key, None)
    
    # Удаляем сообщение, если оно есть
    try:
        await update.message.delete()
    except Exception:
        pass
    
    await update.message.reply_text(
        "👑 Панель администратора\n\nВыберите действие:",
        reply_markup=get_admin_reply_keyboard()
    )

async def content_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда управления контентом"""
    if not is_admin(update.effective_user.id):
        return
    
    await update.message.delete()
    await update.message.reply_text(
        "🧠 Контент-задания\nВыбери, с чем хочешь работать:",
        reply_markup=get_content_reply_keyboard()
    )

async def content_add_meme_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик добавления мема"""
    if not is_admin(update.effective_user.id):
        return
    
    await update.message.delete()
    context.user_data.pop('content_stage', None)
    await update.message.reply_text("📥 Пришлите мем (JPG/PNG):")
    context.user_data['content_stage'] = CONTENT_STAGE_ADD_MEME

async def content_delete_meme_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик удаления мема"""
    if not is_admin(update.effective_user.id):
        return
    
    await update.message.delete()
    
    # Получаем список мемов
    db.cursor.execute("SELECT id, file_path FROM meme_templates")
    memes = db.cursor.fetchall()
    
    if not memes:
        await update.message.reply_text("Нет мемов для удаления.", reply_markup=get_back_inline_keyboard())
        return
    
    msg_lines = ["🗑 Список мемов (ID — файл):"]
    for mid, file_path in memes:
        filename = os.path.basename(file_path)
        snippet = filename if len(filename) <= 30 else filename[:30] + "..."
        msg_lines.append(f"{mid} — {snippet}")
    msg_lines.append("\nПришлите ID мема для удаления.")
    
    await update.message.reply_text("\n".join(msg_lines))
    context.user_data['content_stage'] = CONTENT_STAGE_DELETE_MEME

async def content_list_chats_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик списка чатов"""
    if not is_admin(update.effective_user.id):
        return
    
    await update.message.delete()
    
    db.cursor.execute("SELECT chat_username FROM allowed_chats ORDER BY RANDOM()")
    chats = [row[0] for row in db.cursor.fetchall()]
    
    if not chats:
        await update.message.reply_text("Список чатов пуст.", reply_markup=get_back_inline_keyboard())
        return
    
    msg = "📋 Список чатов:\n" + "\n".join(f"{i+1}. {chat}" for i, chat in enumerate(chats))
    await update.message.reply_text(msg, reply_markup=get_back_inline_keyboard())

async def content_add_chat_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик добавления чата"""
    if not is_admin(update.effective_user.id):
        return
    
    await update.message.delete()
    context.user_data['content_stage'] = CONTENT_STAGE_ADD_CHAT
    await update.message.reply_text("➕ Введите @username, t.me/... или полную ссылку на чат:")

async def content_delete_chat_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик удаления чата"""
    if not is_admin(update.effective_user.id):
        return
    
    await update.message.delete()
    
    # Получаем чаты в отсортированном порядке
    db.cursor.execute("SELECT chat_username FROM allowed_chats ORDER BY chat_username")
    chats = [row[0] for row in db.cursor.fetchall()]
    
    # Сохраняем упорядоченный список для удаления
    context.user_data['delete_chats_list'] = chats
    
    if not chats:
        await update.message.reply_text("Нет чатов для удаления.", reply_markup=get_back_inline_keyboard())
        return
    
    msg = "🗑 Список чатов:\n" + "\n".join(f"{i+1}. {chat}" for i, chat in enumerate(chats)) + "\n\nПришлите номер для удаления."
    await update.message.reply_text(msg)
    context.user_data['content_stage'] = CONTENT_STAGE_DELETE_CHAT

async def content_add_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик добавления текста"""
    if not is_admin(update.effective_user.id):
        return
    
    try:
        await update.message.delete()
    except Exception:
        pass
    
    context.user_data['content_stage'] = CONTENT_STAGE_ADD_TEXT
    await update.message.reply_text("✍️ Введите текст для нового задания:")

async def content_list_texts_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик списка текстов"""
    if not is_admin(update.effective_user.id):
        return
    
    await update.message.delete()
    
    db.cursor.execute("SELECT id, text FROM text_templates")
    rows = db.cursor.fetchall()
    
    if not rows:
        await update.message.reply_text("Список текстов пуст.", reply_markup=get_back_inline_keyboard())
        return
    
    msg_lines = ["🧾 Список текстов (ID — начало текста):"]
    for tid, txt in rows:
        snippet = txt if len(txt) <= 30 else txt[:30] + "..."
        msg_lines.append(f"{tid} — {snippet}")
    msg_lines.append("\nПришлите ID текста для удаления.")
    
    await update.message.reply_text("\n".join(msg_lines))
    context.user_data['content_stage'] = CONTENT_STAGE_LIST_TEXTS

async def promo_panel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Панель управления промо"""
    if not is_admin(update.effective_user.id):
        return
    
    await update.message.delete()
    await update.message.reply_text(
        "💎 Promo-оферы\nВыберите действие:",
        reply_markup=get_promo_reply_keyboard()
    )

async def promo_add_offer_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик добавления промо-оффера"""
    if not is_admin(update.effective_user.id):
        return
    
    await update.message.delete()
    context.user_data['promo_stage'] = PROMO_STAGE_ADD
    await update.message.reply_text("📥 Введите оффер в формате: Название — стоимость (целое число)")

async def promo_delete_offer_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик удаления промо-оффера"""
    if not is_admin(update.effective_user.id):
        return
    
    await update.message.delete()
    
    db.cursor.execute("SELECT offer_id, title, cost FROM promo_offers")
    rows = db.cursor.fetchall()
    
    if not rows:
        await update.message.reply_text("Нет офферов для удаления.", reply_markup=get_back_inline_keyboard())
        return
    
    msg_lines = ["🗑 Список офферов (ID — Название — Стоимость):"]
    for oid, title, cost in rows:
        msg_lines.append(f"{oid} — {title} — {cost}")
    msg_lines.append("\nПришлите ID оффера для удаления.")
    
    await update.message.reply_text("\n".join(msg_lines))
    context.user_data['promo_stage'] = PROMO_STAGE_DELETE

async def promo_list_offers_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик списка промо-офферов"""
    if not is_admin(update.effective_user.id):
        return
    
    await update.message.delete()
    
    db.cursor.execute("SELECT offer_id, title, cost FROM promo_offers")
    rows = db.cursor.fetchall()
    
    if not rows:
        await update.message.reply_text("Список офферов пуст.", reply_markup=get_back_inline_keyboard())
        return
    
    lines = ["📋 Список офферов (ID — Название — Стоимость):"]
    for oid, title, cost in rows:
        lines.append(f"{oid} — {title} — {cost}")
    
    await update.message.reply_text("\n".join(lines), reply_markup=get_back_inline_keyboard())

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда статистики"""
    if not is_admin(update.effective_user.id):
        return
    
    today_start, week_start = get_date_range()
    
    # Всего пользователей
    db.cursor.execute("SELECT COUNT(*) FROM users")
    total = db.cursor.fetchone()[0]
    
    # Пришло сегодня
    db.cursor.execute(
        "SELECT COUNT(*) FROM users WHERE joined_date >= ?",
        (today_start.isoformat(),)
    )
    today_count = db.cursor.fetchone()[0]
    
    # Пришло за неделю
    db.cursor.execute(
        "SELECT COUNT(*) FROM users WHERE joined_date >= ?",
        (week_start.isoformat(),)
    )
    week_count = db.cursor.fetchone()[0]
    
    text = get_stats_text(today_count, week_count, total)
    await update.message.reply_text(
        text, 
        parse_mode=ParseMode.HTML, 
        reply_markup=get_users_file_keyboard()
    )

async def check_db_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Проверка состояния базы данных (только для админов)"""
    if not is_admin(update.effective_user.id):
        return
    
    await update.message.delete()
    
    try:
        # Проверяем размер файла БД
        import os
        db_size = os.path.getsize('bot_database.db')
        
        # Проверяем количество пользователей
        db.cursor.execute("SELECT COUNT(*) FROM users")
        user_count = db.cursor.fetchone()[0]
        
        # Проверяем последних пользователей
        db.cursor.execute("""
            SELECT user_id, username, joined_date 
            FROM users 
            ORDER BY joined_date DESC 
            LIMIT 3
        """)
        recent_users = db.cursor.fetchall()
        
        # Проверяем целостность БД
        db.cursor.execute("PRAGMA integrity_check")
        integrity_result = db.cursor.fetchone()
        
        status_text = (
            f"📊 <b>СОСТОЯНИЕ БАЗЫ ДАННЫХ</b>\n\n"
            f"📁 Размер файла: {db_size:,} байт\n"
            f"👥 Пользователей: {user_count}\n"
            f"🔍 Целостность: {'✅ OK' if integrity_result[0] == 'ok' else '❌ ОШИБКА'}\n\n"
            f"📅 <b>Последние пользователи:</b>\n"
        )
        
        for user_id, username, joined_date in recent_users:
            status_text += f"   {user_id} (@{username or 'нет'}) - {joined_date}\n"
        
        await update.message.reply_text(status_text, parse_mode=ParseMode.HTML)
        
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка проверки БД: {e}")

async def send_users_file_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик отправки файла пользователей"""
    query = update.callback_query
    user_id = query.from_user.id
    
    if not is_admin(user_id):
        await query.answer("Нет доступа", show_alert=True)
        return
    
    await query.answer()
    
    # Получаем список пользователей
    db.cursor.execute("SELECT user_id, username, first_name, last_name, ref_by, joined_date FROM users")
    rows = db.cursor.fetchall()
    
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

async def broadcast_panel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Панель рассылки"""
    if not is_admin(update.effective_user.id):
        return
    
    await update.message.delete()
    await update.message.reply_text(
        "Выберите режим рассылки:",
        reply_markup=get_broadcast_keyboard()
    )

async def handle_admin_broadcast_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик админских сообщений для рассылки"""
    if not is_admin(update.effective_user.id):
        return
    
    mode = context.user_data.get('broadcast_mode')
    if not mode:
        return
    
    msg = update.message
    text = msg.text or msg.caption or ""
    photo = msg.photo[-1] if msg.photo else None
    sent, errors = 0, 0
    
    if mode == 'all':
        users = db.get_all_users()
        for uid in users:
            try:
                if photo:
                    file = await photo.get_file()
                    os.makedirs(SCREENSHOTS_DIR, exist_ok=True)
                    path = os.path.join(SCREENSHOTS_DIR, f"bc_{uid}.jpg")
                    await file.download_to_drive(path)
                    await context.bot.send_photo(
                        chat_id=uid, 
                        photo=open(path,'rb'), 
                        caption=text, 
                        parse_mode=ParseMode.HTML
                    )
                else:
                    await context.bot.send_message(
                        chat_id=uid, 
                        text=text, 
                        parse_mode=ParseMode.HTML
                    )
                sent += 1
            except:
                errors += 1
    
    elif mode == 'user':
        parts = text.split(' ', 1)
        if len(parts) < 2:
            await update.message.reply_text(
                "Неверный формат. Нужно: `@username текст`", 
                parse_mode=ParseMode.HTML
            )
            return
        
        uname, body = parts
        uid = db.get_user_by_username(uname.lstrip('@'))
        
        if not uid:
            await update.message.reply_text("Пользователь не найден.")
            return
        
        try:
            if photo:
                file = await photo.get_file()
                os.makedirs(SCREENSHOTS_DIR, exist_ok=True)
                path = os.path.join(SCREENSHOTS_DIR, f"bc_{uid}.jpg")
                await file.download_to_drive(path)
                await context.bot.send_photo(
                    chat_id=uid, 
                    photo=open(path,'rb'), 
                    caption=body, 
                    parse_mode=ParseMode.MARKDOWN_V2
                )
            else:
                await context.bot.send_message(
                    chat_id=uid, 
                    text=body, 
                    parse_mode=ParseMode.MARKDOWN_V2
                )
            sent = 1
        except:
            errors = 1
    
    context.user_data['broadcast_mode'] = None
    await update.message.reply_text(f"Рассылка завершена: {sent} успешно, {errors} ошибок.")

async def handle_admin_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик админского ввода"""
    if not is_admin(update.effective_user.id):
        return
    
    # Убираем обработку "Статистика" - теперь она обрабатывается отдельным обработчиком
    # if update.message.text == "Статистика":
    #     await stats_command(update, context)
    #     return
    
    # Текущее состояние админ-флоу по контенту
    content_stage = context.user_data.get('content_stage')
    stage = context.user_data.get('task_stage')
    
    # Обработка промо-кода для задания
    if stage == 'await_promo_code' and update.message.text:
        prompt_id = context.user_data.pop('promo_prompt_msg_id', None)
        if prompt_id:
            await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=prompt_id)
        
        await update.message.delete()
        code = update.message.text.strip()
        task_id = context.user_data['task_id']
        user_id = context.user_data['task_user_id']
        
        # Обновляем статус задания
        db.approve_task(task_id, user_id)
        
        # Сохраняем купон
        db.cursor.execute("INSERT INTO coupons (code, type) VALUES (?, ?)", (code, 'promo'))
        db.conn.commit()
        
        # Уведомляем пользователя
        await context.bot.send_message(
            chat_id=user_id,
            text=f"🎉 Поздравляем! Ваш купон: {code}"
        )
        
        await update.message.reply_text(
            "Купон отправлен пользователю.", 
            reply_markup=get_back_inline_keyboard()
        )
        context.user_data['task_stage'] = None
        return
    
    # Добавление мема
    if content_stage == CONTENT_STAGE_ADD_MEME and update.message and update.message.photo:
        photo = update.message.photo[-1]
        file = await photo.get_file()
        os.makedirs(MEMES_DIR, exist_ok=True)
        path = os.path.join(MEMES_DIR, f"meme_{file.file_id}.jpg")
        await file.download_to_drive(path)
        
        # Сохраняем в БД с пустым текстом
        db.cursor.execute(
            "INSERT INTO meme_templates (file_path, text) VALUES (?, ?)",
            (path, "")
        )
        db.conn.commit()
        
        await update.message.reply_text("✅ Мем добавлен.", reply_markup=get_back_inline_keyboard())
        context.user_data['content_stage'] = None
        return
    
    # Удаление мема по ID
    if content_stage == CONTENT_STAGE_DELETE_MEME and update.message and update.message.text:
        text = update.message.text.strip()
        if text.isdigit():
            meme_id = int(text)
            if db.delete_meme(meme_id):
                await update.message.reply_text("✅ Мем удалён из базы данных и файл удалён.", reply_markup=get_back_inline_keyboard())
            else:
                await update.message.reply_text("❌ Мем с таким ID не найден.", reply_markup=get_back_inline_keyboard())
            context.user_data['content_stage'] = None
        else:
            await update.message.reply_text(
                "❌ Некорректный ID. Пришлите номер мема для удаления.", 
                reply_markup=get_back_inline_keyboard()
            )
        return
    
    # Добавление чата
    if content_stage == CONTENT_STAGE_ADD_CHAT and update.message and update.message.text:
        chat = update.message.text.strip()
        if not (chat.startswith('@') or chat.startswith('t.me/') or chat.startswith('http')):
            await update.message.reply_text(
                "❌ Некорректный формат. Введите @username, t.me/... или полную ссылку на чат.",
                reply_markup=get_back_inline_keyboard()
            )
            return
        
        db.cursor.execute("INSERT OR IGNORE INTO allowed_chats (chat_username) VALUES (?)", (chat,))
        db.conn.commit()
        await update.message.reply_text(f"✅ Чат {chat} добавлен.", reply_markup=get_back_inline_keyboard())
        context.user_data['content_stage'] = None
        return
    
    # Удаление чата по номеру
    if content_stage == CONTENT_STAGE_DELETE_CHAT and update.message and update.message.text.isdigit():
        idx = int(update.message.text.strip()) - 1
        chats = context.user_data.get('delete_chats_list', [])
        
        if 0 <= idx < len(chats):
            removed = chats[idx]
            db.cursor.execute("DELETE FROM allowed_chats WHERE chat_username = ?", (removed,))
            db.conn.commit()
            await update.message.reply_text(f"✅ Чат {removed} удалён.", reply_markup=get_back_inline_keyboard())
        else:
            await update.message.reply_text(
                "❌ Некорректный номер. Пришлите число из списка.", 
                reply_markup=get_back_inline_keyboard()
            )
        
        context.user_data.pop('delete_chats_list', None)
        context.user_data['content_stage'] = None
        return
    
    # Добавление промо-оффера
    if context.user_data.get('promo_stage') == PROMO_STAGE_ADD and update.message and update.message.text:
        text = update.message.text.strip()
        if '—' in text:
            title, cost_str = [s.strip() for s in text.split('—', 1)]
            if cost_str.isdigit():
                cost = int(cost_str)
                db.cursor.execute("INSERT INTO promo_offers (title, cost) VALUES (?, ?)", (title, cost))
                db.conn.commit()
                await update.message.reply_text(
                    f"✅ Оффер '{title}' за {cost} преданных добавлен.", 
                    reply_markup=get_back_inline_keyboard()
                )
                context.user_data['promo_stage'] = None
            else:
                await update.message.reply_text(
                    "❌ Неверная стоимость. Введите целое число после —.", 
                    reply_markup=get_back_inline_keyboard()
                )
        else:
            await update.message.reply_text(
                "❌ Неверный формат. Используйте: Название — стоимость", 
                reply_markup=get_back_inline_keyboard()
            )
        return
    
    # Удаление промо-оффера по ID
    if context.user_data.get('promo_stage') == PROMO_STAGE_DELETE and update.message and update.message.text.isdigit():
        oid = int(update.message.text.strip())
        db.cursor.execute("DELETE FROM promo_offers WHERE offer_id = ?", (oid,))
        db.conn.commit()
        await update.message.reply_text(f"✅ Оффер {oid} удалён.", reply_markup=get_back_inline_keyboard())
        context.user_data['promo_stage'] = None
        return
    
    # Удаление текста по ID
    if context.user_data.get('content_stage') == CONTENT_STAGE_LIST_TEXTS and update.message and update.message.text:
        text_id = update.message.text.strip()
        if text_id.isdigit():
            tid = int(text_id)
            db.cursor.execute("DELETE FROM text_templates WHERE id = ?", (tid,))
            db.conn.commit()
            await update.message.reply_text("✅ Текст удалён.", reply_markup=get_back_inline_keyboard())
            context.user_data['content_stage'] = None
        else:
            await update.message.reply_text(
                "❌ Некорректный ID. Пришлите корректный номер текста.", 
                reply_markup=get_back_inline_keyboard()
            )
        return
    
    # Добавление текста
    if content_stage == CONTENT_STAGE_ADD_TEXT and update.message:
        text = getattr(update.message, "text_html", None) or update.message.text or ""
        db.cursor.execute("INSERT INTO text_templates (text) VALUES (?)", (text,))
        db.conn.commit()
        await update.message.reply_text("✅ Текст добавлен.", reply_markup=get_back_inline_keyboard())
        context.user_data['content_stage'] = None
        return
    
    # Обработка рассылки
    stage_bc = context.user_data.get('broadcast_stage')
    if stage_bc == BROADCAST_STAGE_TEXT and update.message.text:
        text = update.message.text
        context.user_data['broadcast_text'] = text
        await update.message.delete()
        
        from keyboards import InlineKeyboardMarkup, InlineKeyboardButton
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
        
        from keyboards import InlineKeyboardMarkup, InlineKeyboardButton
        await update.message.reply_text(
            "Фото сохранено. Готовы отправить рассылку?",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Да", callback_data='bc_execute')],
                [InlineKeyboardButton("🔙 Назад", callback_data='task_back')],
            ]),
            parse_mode=ParseMode.MARKDOWN_V2
        )

async def clear_chat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Очистка чата"""
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    
    # Только админ может чистить в группе или канале, в личке можно всегда
    if not is_admin(user_id) and update.effective_chat.type != ChatType.PRIVATE:
        await update.message.reply_text("Нет прав для очистки.")
        return
    
    # Получаем последние 50 сообщений в чате
    async for msg in context.bot.get_chat_history(chat_id, limit=50):
        # Оставить приветственное сообщение (по фразе)
        if "AMB Promo — ты в игре!" in (msg.text or ""):
            continue
        try:
            await context.bot.delete_message(chat_id, msg.message_id)
        except Exception:
            pass
    
    await context.bot.send_message(chat_id, "Чат очищен. Приветствие осталось.")

async def debug_subscription_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда диагностики подписки"""
    if not is_admin(update.effective_user.id):
        return
    
    # Проверяем, есть ли ID пользователя в сообщении
    if not context.args:
        await update.message.reply_text(
            "🔍 Диагностика подписки\n\n"
            "Использование: /debug_sub <user_id>\n"
            "Пример: /debug_sub 123456789"
        )
        return
    
    try:
        user_id = int(context.args[0])
        debug_info = await debug_subscription(context.bot, user_id)
        
        # Формируем отчет
        report = f"🔍 <b>Диагностика подписки</b>\n\n"
        report += f"👤 <b>Пользователь:</b> {user_id}\n"
        report += f"📢 <b>Канал:</b> {debug_info['channel_id']}\n\n"
        
        if debug_info['error']:
            report += f"❌ <b>Ошибка:</b> {debug_info['error']}\n"
        else:
            if debug_info['bot_can_access_channel']:
                report += "✅ <b>Бот имеет доступ к каналу</b>\n"
                if debug_info['channel_info']:
                    channel = debug_info['channel_info']
                    report += f"📢 <b>Название:</b> {channel['title']}\n"
                    report += f"🆔 <b>ID:</b> {channel['id']}\n"
                    report += f"📝 <b>Тип:</b> {channel['type']}\n"
                    if channel['username']:
                        report += f"🔗 <b>Username:</b> @{channel['username']}\n"
                    report += "\n"
                
                if debug_info['user_status']:
                    status = debug_info['user_status']
                    report += f"👤 <b>Статус пользователя:</b> {status['status']}\n"
                    report += f"✅ <b>Подписан:</b> {'Да' if status['is_member'] else 'Нет'}\n"
                    report += f"👑 <b>Создатель:</b> {'Да' if status['is_creator_status'] else 'Нет'}\n"
                    report += f"⚡ <b>Админ:</b> {'Да' if status['is_admin_status'] else 'Нет'}\n"
                    if status['until_date']:
                        report += f"⏰ <b>До:</b> {status['until_date']}\n"
            else:
                report += "❌ <b>Бот не имеет доступа к каналу</b>\n"
        
        await update.message.reply_text(report, parse_mode=ParseMode.HTML)
        
    except ValueError:
        await update.message.reply_text("❌ Неверный ID пользователя. Используйте число.")
    except Exception as e:
        logger.error(f"Debug subscription command failed: {e}")
        await update.message.reply_text(f"❌ Ошибка при диагностике: {e}")

async def clear_cache_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Команда очистки кэша подписки"""
    if not is_admin(update.effective_user.id):
        return
    
    # Проверяем, есть ли ID пользователя в сообщении
    if not context.args:
        # Очищаем весь кэш
        clear_subscription_cache()
        await update.message.reply_text("✅ Кэш подписки очищен для всех пользователей")
    else:
        try:
            user_id = int(context.args[0])
            clear_subscription_cache(user_id)
            await update.message.reply_text(f"✅ Кэш подписки очищен для пользователя {user_id}")
        except ValueError:
            await update.message.reply_text("❌ Неверный ID пользователя. Используйте число.")
        except Exception as e:
            logger.error(f"Clear cache command failed: {e}")
            await update.message.reply_text(f"❌ Ошибка при очистке кэша: {e}") 
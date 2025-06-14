import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import os
import sys
import atexit

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
from sqlalchemy.orm import sessionmaker
from telegram.error import Conflict, NetworkError

from models import engine, Base, Client, Appointment, Schedule
from schedule_handler import ScheduleHandler
from appointment_handler import AppointmentHandler
from config import (
    BOT_TOKEN, ADMIN_ID, PHOTOS_DIR, WORK_START_TIME, WORK_END_TIME,
    LUNCH_START_TIME, LUNCH_END_TIME, APPOINTMENT_DURATION, SCHEDULE_DAYS_AHEAD
)

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Создаем сессию для работы с базой данных
Session = sessionmaker(bind=engine)
session = Session()

# Создаем обработчики
schedule_handler = ScheduleHandler(session)
appointment_handler = AppointmentHandler(session)

# Создаем клавиатуры
def get_admin_keyboard():
    keyboard = [
        [InlineKeyboardButton("Расписание", callback_data="schedule")],
        [InlineKeyboardButton("Записи", callback_data="appointments")],
        [InlineKeyboardButton("О боте", callback_data="about")],
        [InlineKeyboardButton("Поделиться", callback_data="share")]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_client_keyboard():
    keyboard = [
        [InlineKeyboardButton("Записаться", callback_data="book")],
        [InlineKeyboardButton("О боте", callback_data="about")],
        [InlineKeyboardButton("Поделиться", callback_data="share")]
    ]
    return InlineKeyboardMarkup(keyboard)

# Обработчики команд
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    keyboard = get_admin_keyboard() if user_id == ADMIN_ID else get_client_keyboard()
    await update.message.reply_text(
        "Добро пожаловать! Выберите действие:",
        reply_markup=keyboard
    )

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "back_to_menu":
        keyboard = get_admin_keyboard() if query.from_user.id == ADMIN_ID else get_client_keyboard()
        await query.edit_message_text(
            "Выберите действие:",
            reply_markup=keyboard
        )
        return

    if query.data == "schedule":
        await schedule_handler.show_schedule(update, context)
    elif query.data == "fill_schedule":
        await schedule_handler.show_schedule_filling(update, context)
    elif query.data.startswith("date_"):
        await schedule_handler.handle_date_selection(update, context)
    elif query.data.startswith("time_"):
        await schedule_handler.handle_time_selection(update, context)
    elif query.data == "book":
        await appointment_handler.start_appointment_creation(update, context)
    elif query.data == "about":
        await show_about(update, context)
    elif query.data == "share":
        await handle_share(update, context)

async def handle_share(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    bot = await context.bot.get_me()
    share_text = (
        f"Привет! Я нашел полезного бота для записи к подологу: @{bot.username}\n\n"
        "С его помощью можно:\n"
        "• Записаться на прием\n"
        "• Выбрать удобное время\n"
        "• Отправить фото проблемы\n"
        "• Получить подтверждение записи\n\n"
        "Попробуйте сами!"
    )
    keyboard = [[InlineKeyboardButton("Поделиться ботом", url=f"https://t.me/share/url?url=https://t.me/{bot.username}&text={share_text}")]]
    await query.edit_message_text(
        share_text,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def show_about(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    about_text = (
        "🤖 Бот для записи к подологу\n\n"
        "• Удобная запись на прием\n"
        "• Выбор удобного времени\n"
        "• Возможность отправить фото\n"
        "• Подтверждение записи\n\n"
        "Для возврата в главное меню нажмите кнопку ниже."
    )
    keyboard = [[InlineKeyboardButton("◀️ Назад", callback_data="back_to_menu")]]
    await query.edit_message_text(
        about_text,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.photo:
        await appointment_handler.handle_photo(update, context)
    else:
        await appointment_handler.handle_text(update, context)

def check_pid():
    """Проверяет, не запущен ли уже бот"""
    pid = str(os.getpid())
    pidfile = "bot.pid"

    if os.path.isfile(pidfile):
        with open(pidfile, 'r') as f:
            old_pid = f.read().strip()
        if os.path.exists(f"/proc/{old_pid}"):
            print(f"Бот уже запущен с PID {old_pid}")
            sys.exit(1)
    
    with open(pidfile, 'w') as f:
        f.write(pid)
    
    def remove_pidfile():
        os.remove(pidfile)
    
    atexit.register(remove_pidfile)

def main():
    # Проверяем, не запущен ли уже бот
    check_pid()
    
    # Создаем приложение
    application = Application.builder().token(BOT_TOKEN).build()

    # Добавляем обработчики
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(handle_callback))
    application.add_handler(MessageHandler(filters.PHOTO, handle_message))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Запускаем бота
    application.run_polling()

if __name__ == '__main__':
    main() 
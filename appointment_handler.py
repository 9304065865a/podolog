import os
import logging
from datetime import datetime
from typing import Optional
from sqlalchemy.orm import Session
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from models import Client, Appointment, Schedule
from config import PHOTOS_DIR, APPOINTMENT_DURATION

logger = logging.getLogger(__name__)

class AppointmentManager:
    """Класс для управления записями клиентов"""
    
    def __init__(self, session: Session):
        self.session = session
        self.temp_data = {}

    async def start_appointment_creation(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        user_id = query.from_user.id
        
        # Проверяем, есть ли активная запись
        if user_id in self.temp_data:
            await query.edit_message_text(
                "У вас уже есть активная запись. Хотите начать заново?",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("Да", callback_data="restart_appointment")],
                    [InlineKeyboardButton("Нет", callback_data="back_to_menu")]
                ])
            )
            return

        # Инициализируем данные для новой записи
        self.temp_data[user_id] = {
            'step': 'name',
            'name': None,
            'phone': None,
            'description': None,
            'photo_path': None,
            'date': None,
            'time': None
        }

        await query.edit_message_text(
            "Пожалуйста, введите ваше имя:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Отмена", callback_data="cancel_appointment")]])
        )

    async def handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if user_id not in self.temp_data:
            await update.message.reply_text(
                "Пожалуйста, начните создание записи, нажав кнопку 'Записаться'."
            )
            return

        data = self.temp_data[user_id]
        text = update.message.text

        if data['step'] == 'name':
            data['name'] = text
            data['step'] = 'phone'
            await update.message.reply_text(
                "Введите ваш номер телефона:",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Отмена", callback_data="cancel_appointment")]])
            )
        elif data['step'] == 'phone':
            data['phone'] = text
            data['step'] = 'description'
            await update.message.reply_text(
                "Опишите вашу проблему:",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Отмена", callback_data="cancel_appointment")]])
            )
        elif data['step'] == 'description':
            data['description'] = text
            data['step'] = 'photo'
            await update.message.reply_text(
                "Хотите прикрепить фото?",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("Да", callback_data="add_photo")],
                    [InlineKeyboardButton("Нет", callback_data="skip_photo")],
                    [InlineKeyboardButton("◀️ Отмена", callback_data="cancel_appointment")]
                ])
            )

    async def handle_photo(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if user_id not in self.temp_data or self.temp_data[user_id]['step'] != 'photo':
            await update.message.reply_text(
                "Пожалуйста, начните создание записи, нажав кнопку 'Записаться'."
            )
            return

        # Получаем фото
        photo = update.message.photo[-1]
        file = await context.bot.get_file(photo.file_id)
        
        # Создаем директорию для фото, если её нет
        os.makedirs(PHOTOS_DIR, exist_ok=True)
        
        # Сохраняем фото
        file_path = os.path.join(PHOTOS_DIR, f"{user_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg")
        await file.download_to_drive(file_path)
        
        self.temp_data[user_id]['photo_path'] = file_path
        self.temp_data[user_id]['step'] = 'date'
        
        await update.message.reply_text(
            "Фото успешно сохранено! Теперь выберите дату:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Отмена", callback_data="cancel_appointment")]])
        )

    async def cancel_appointment_creation(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        user_id = query.from_user.id
        
        if user_id in self.temp_data:
            # Удаляем сохраненное фото, если оно есть
            if self.temp_data[user_id].get('photo_path'):
                try:
                    os.remove(self.temp_data[user_id]['photo_path'])
                except:
                    pass
            
            # Очищаем временные данные
            self.temp_data.pop(user_id)
        
        await query.edit_message_text(
            "Создание записи отменено.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data="back_to_menu")]])
        )

    def clear_appointment_data(self, user_id):
        """Очищает временные данные записи"""
        if user_id in self.temp_data:
            # Удаляем сохраненное фото, если оно есть
            if self.temp_data[user_id].get('photo_path'):
                try:
                    os.remove(self.temp_data[user_id]['photo_path'])
                except:
                    pass
            
            # Очищаем временные данные
            self.temp_data.pop(user_id)

    async def handle_appointment_time(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик времени записи"""
        try:
            time_str = update.message.text
            time = datetime.strptime(time_str, "%H:%M").time()
            date = context.user_data.get('appointment_date')
            
            # Проверяем, не занято ли это время
            existing_appointment = self.session.query(Appointment).filter(
                Appointment.date == date,
                Appointment.time == time
            ).first()
            
            if existing_appointment:
                await update.message.reply_text(
                    "К сожалению, это время уже занято. Пожалуйста, выберите другое время."
                )
                return
            
            # Создаем запись
            appointment = Appointment(
                client_name=context.user_data['client_name'],
                phone=context.user_data['client_phone'],
                problem_description=context.user_data['problem_description'],
                date=date,
                time=time,
                photo_path=context.user_data.get('photo_path')
            )
            
            self.session.add(appointment)
            self.session.commit()
            
            # Формируем информативное сообщение о подтверждении
            confirmation_message = (
                "✅ *Запись успешно создана!*\n\n"
                f"👤 *Клиент:* {appointment.client_name}\n"
                f"📅 *Дата:* {appointment.date.strftime('%d.%m.%Y')}\n"
                f"🕐 *Время:* {appointment.time.strftime('%H:%M')}\n"
                f"📞 *Телефон:* {appointment.phone}\n"
                f"📝 *Описание проблемы:* {appointment.problem_description}\n"
            )
            
            if appointment.photo_path:
                confirmation_message += "\n📸 *Фото прикреплено*"
            
            # Отправляем подтверждение клиенту
            await update.message.reply_text(
                confirmation_message,
                parse_mode='Markdown'
            )
            
            # Если это админ, отправляем дополнительное сообщение
            if context.user_data.get('is_admin'):
                await update.message.reply_text(
                    "Запись добавлена в базу данных. Вы можете просмотреть все записи в разделе 'Найти клиента'."
                )
            
            # Очищаем данные
            self.clear_appointment_data(context)
            
        except ValueError:
            await update.message.reply_text(
                "Пожалуйста, введите время в формате ЧЧ:ММ (например, 14:30)"
            )

    async def show_available_times(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показывает доступное время для записи"""
        # TODO: Реализовать показ доступного времени
        await update.message.reply_text("Функция выбора времени будет доступна в следующем обновлении.") 
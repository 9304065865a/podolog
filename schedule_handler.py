from datetime import datetime, timedelta
from typing import List, Optional
from sqlalchemy.orm import Session
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
import logging

from models import Schedule, Appointment
from config import (
    WORK_START_TIME, WORK_END_TIME, LUNCH_START_TIME, LUNCH_END_TIME,
    APPOINTMENT_DURATION, SCHEDULE_DAYS_AHEAD
)

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ScheduleManager:
    """Класс для управления расписанием"""
    
    def __init__(self, session: Session):
        self.session = session
        self.temp_data = {}

    async def show_schedule(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        user_id = query.from_user.id

        # Получаем расписание на следующие 10 дней
        end_date = datetime.now() + timedelta(days=SCHEDULE_DAYS_AHEAD)
        schedule = self.session.query(Schedule).filter(
            Schedule.date >= datetime.now().date(),
            Schedule.date <= end_date.date()
        ).all()

        if not schedule:
            message = "Расписание на следующие 10 дней пусто."
            keyboard = []
            if user_id == context.bot_data.get('admin_id'):
                keyboard.append([InlineKeyboardButton("Заполнить расписание", callback_data="fill_schedule")])
            keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="back_to_menu")])
            await query.edit_message_text(
                message,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return

        # Формируем сообщение с расписанием
        message = "Расписание на следующие 10 дней:\n\n"
        current_date = None
        for entry in schedule:
            if entry.date.date() != current_date:
                current_date = entry.date.date()
                message += f"\n📅 {current_date.strftime('%d.%m.%Y')}:\n"
            if entry.is_working_day:
                message += f"🕒 {entry.start_time.strftime('%H:%M')} - {entry.end_time.strftime('%H:%M')}\n"
            else:
                message += "❌ Выходной\n"

        # Добавляем кнопки управления
        keyboard = []
        if user_id == context.bot_data.get('admin_id'):
            keyboard.append([InlineKeyboardButton("Редактировать расписание", callback_data="fill_schedule")])
        keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="back_to_menu")])

        await query.edit_message_text(
            message,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    async def show_schedule_filling(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        keyboard = []
        
        # Создаем кнопки для выбора даты
        for i in range(SCHEDULE_DAYS_AHEAD):
            date = datetime.now() + timedelta(days=i)
            keyboard.append([
                InlineKeyboardButton(
                    date.strftime("%d.%m.%Y"),
                    callback_data=f"date_{date.strftime('%Y-%m-%d')}"
                )
            ])
        
        keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="back_to_menu")])
        
        await query.edit_message_text(
            "Выберите дату для заполнения расписания:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    async def handle_date_selection(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        date_str = query.data.split('_')[1]
        selected_date = datetime.strptime(date_str, '%Y-%m-%d')
        
        # Сохраняем выбранную дату
        self.temp_data[query.from_user.id] = {'date': selected_date}
        
        # Создаем кнопки для выбора времени начала
        keyboard = []
        current_time = WORK_START_TIME
        while current_time < WORK_END_TIME:
            if not (LUNCH_START_TIME <= current_time <= LUNCH_END_TIME):
                keyboard.append([
                    InlineKeyboardButton(
                        current_time.strftime("%H:%M"),
                        callback_data=f"time_start_{current_time.strftime('%H:%M')}"
                    )
                ])
            current_time += timedelta(minutes=APPOINTMENT_DURATION)
        
        keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="fill_schedule")])
        
        await query.edit_message_text(
            f"Выберите время начала для {selected_date.strftime('%d.%m.%Y')}:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    async def handle_time_selection(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        user_id = query.from_user.id
        time_type, time_str = query.data.split('_')[1:]
        selected_time = datetime.strptime(time_str, '%H:%M').time()
        
        if time_type == 'start':
            # Сохраняем время начала
            self.temp_data[user_id]['start_time'] = selected_time
            
            # Создаем кнопки для выбора времени окончания
            keyboard = []
            current_time = selected_time
            while current_time < WORK_END_TIME:
                if not (LUNCH_START_TIME <= current_time <= LUNCH_END_TIME):
                    keyboard.append([
                        InlineKeyboardButton(
                            current_time.strftime("%H:%M"),
                            callback_data=f"time_end_{current_time.strftime('%H:%M')}"
                        )
                    ])
                current_time = (datetime.combine(datetime.today(), current_time) + 
                              timedelta(minutes=APPOINTMENT_DURATION)).time()
            
            keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data=f"date_{self.temp_data[user_id]['date'].strftime('%Y-%m-%d')}")])
            
            await query.edit_message_text(
                "Выберите время окончания:",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        else:  # time_type == 'end'
            # Сохраняем время окончания и сохраняем расписание
            self.temp_data[user_id]['end_time'] = selected_time
            await self.save_schedule(update, context)

    async def save_schedule(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        user_id = query.from_user.id
        data = self.temp_data.get(user_id)
        
        if not data:
            await query.edit_message_text(
                "Произошла ошибка при сохранении расписания. Попробуйте снова.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data="fill_schedule")]])
            )
            return

        try:
            # Удаляем существующие записи на эту дату
            self.session.query(Schedule).filter(
                Schedule.date == data['date'].date()
            ).delete()

            # Создаем новую запись
            schedule_entry = Schedule(
                date=data['date'].date(),
                start_time=datetime.combine(data['date'].date(), data['start_time']),
                end_time=datetime.combine(data['date'].date(), data['end_time']),
                is_working_day=True
            )
            
            self.session.add(schedule_entry)
            self.session.commit()
            
            # Очищаем временные данные
            self.temp_data.pop(user_id, None)
            
            await query.edit_message_text(
                "Расписание успешно сохранено!",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data="fill_schedule")]])
            )
            
        except Exception as e:
            logger.error(f"Ошибка при сохранении расписания: {e}")
            self.session.rollback()
            await query.edit_message_text(
                "Произошла ошибка при сохранении расписания. Попробуйте снова.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("◀️ Назад", callback_data="fill_schedule")]])
            )

    def get_weekday_name(self, date):
        """Возвращает название дня недели на русском"""
        weekdays = {
            0: "Понедельник",
            1: "Вторник",
            2: "Среда",
            3: "Четверг",
            4: "Пятница",
            5: "Суббота",
            6: "Воскресенье"
        }
        return weekdays[date.weekday()]

    async def show_schedule_fill_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показывает меню заполнения расписания"""
        # Получаем текущую дату
        today = datetime.now().date()
        
        # Создаем кнопки для выбора дня
        keyboard = []
        for i in range(10):  # Показываем ближайшие 10 дней
            current_date = today + timedelta(days=i)
            weekday_name = self.get_weekday_name(current_date)
            date_str = current_date.strftime("%d.%m")
            
            keyboard.append([
                InlineKeyboardButton(
                    f"{date_str} {weekday_name}",
                    callback_data=f"select_date_{current_date.strftime('%Y-%m-%d')}"
                )
            ])

        # Добавляем кнопку "Назад"
        keyboard.append([
            InlineKeyboardButton(
                "🔙 Назад",
                callback_data="back_to_menu"
            )
        ])

        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.callback_query.edit_message_text(
            "Выберите день для заполнения расписания:",
            reply_markup=reply_markup
        )

    async def show_time_selection(self, update: Update, context: ContextTypes.DEFAULT_TYPE, date_str: str):
        """Показывает выбор времени для выбранного дня"""
        date = datetime.strptime(date_str, "%Y-%m-%d").date()
        weekday_name = self.get_weekday_name(date)
        
        # Создаем кнопки для выбора времени начала
        keyboard = []
        row = []
        for hour in range(9, 20):  # с 9:00 до 19:00
            time_str = f"{hour:02d}:00"
            row.append(InlineKeyboardButton(
                time_str,
                callback_data=f"select_start_{date_str}_{time_str}"
            ))
            if len(row) == 3:  # по 3 кнопки в ряд
                keyboard.append(row)
                row = []
        if row:  # добавляем оставшиеся кнопки
            keyboard.append(row)

        # Добавляем кнопку "Выходной"
        keyboard.append([
            InlineKeyboardButton(
                "❌ Отметить как выходной",
                callback_data=f"mark_off_{date_str}"
            )
        ])

        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.callback_query.edit_message_text(
            f"Выберите время начала работы на {date.strftime('%d.%m')} ({weekday_name}):",
            reply_markup=reply_markup
        )

    async def show_end_time_selection(self, update: Update, context: ContextTypes.DEFAULT_TYPE, date_str: str, start_time: str):
        """Показывает выбор времени окончания"""
        date = datetime.strptime(date_str, "%Y-%m-%d").date()
        start_hour = int(start_time.split(":")[0])
        
        # Создаем кнопки для выбора времени окончания
        keyboard = []
        row = []
        for hour in range(start_hour + 1, 21):  # от следующего часа до 20:00
            time_str = f"{hour:02d}:00"
            row.append(InlineKeyboardButton(
                time_str,
                callback_data=f"select_end_{date_str}_{start_time}_{time_str}"
            ))
            if len(row) == 3:  # по 3 кнопки в ряд
                keyboard.append(row)
                row = []
        if row:  # добавляем оставшиеся кнопки
            keyboard.append(row)

        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.callback_query.edit_message_text(
            f"Выберите время окончания работы:",
            reply_markup=reply_markup
        )

    async def mark_day_off(self, update: Update, context: ContextTypes.DEFAULT_TYPE, date_str: str):
        """Отмечает день как выходной"""
        date = datetime.strptime(date_str, "%Y-%m-%d").date()
        
        schedule = Schedule(
            date=date,
            start_time=datetime.strptime("00:00", "%H:%M").time(),
            end_time=datetime.strptime("00:00", "%H:%M").time(),
            is_working_day=False
        )
        self.session.add(schedule)
        self.session.commit()
        
        # Показываем подтверждение и предлагаем заполнить следующий день
        next_date = date + timedelta(days=1)
        if next_date <= date + timedelta(days=6):
            keyboard = [[
                InlineKeyboardButton(
                    "📅 Заполнить следующий день",
                    callback_data=f"select_date_{next_date.strftime('%Y-%m-%d')}"
                )
            ]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.callback_query.edit_message_text(
                f"✅ {self.get_weekday_name(date)} ({date.strftime('%d.%m')}) отмечен как выходной день.\n"
                f"Хотите заполнить следующий день?",
                reply_markup=reply_markup
            )
        else:
            await update.callback_query.edit_message_text(
                f"✅ {self.get_weekday_name(date)} ({date.strftime('%d.%m')}) отмечен как выходной день."
            )

    async def get_available_times(self, date: datetime.date) -> list:
        """Получает список доступного времени на указанную дату"""
        schedules = self.session.query(Schedule).filter(
            Schedule.date == date,
            Schedule.is_working_day == True
        ).order_by(Schedule.start_time).all()

        available_times = []
        for schedule in schedules:
            # Проверяем, есть ли уже записи на это время
            appointments = self.session.query(Appointment).filter(
                Appointment.date == date,
                Appointment.time == schedule.start_time
            ).count()

            if appointments == 0:
                available_times.append({
                    'start_time': schedule.start_time,
                    'end_time': schedule.end_time
                })

        return available_times

    async def _show_admin_schedule(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показывает расписание для администратора"""
        # Получаем расписание на следующие 7 дней
        today = datetime.now().date()
        schedule = self.session.query(Schedule).filter(
            Schedule.date >= today,
            Schedule.date <= today + timedelta(days=7)
        ).all()

        if not schedule:
            await update.message.reply_text("Расписание на ближайшую неделю не заполнено.")
            return

        # Формируем сообщение с расписанием
        message = "📅 Расписание на ближайшую неделю:\n\n"
        for day in schedule:
            status = "🟢 Рабочий день" if day.is_working_day else "🔴 Выходной"
            if day.is_self_learning:
                status = "📚 День самообучения"
            message += f"{day.date.strftime('%d.%m.%Y')}: {status}\n"

        # Создаем клавиатуру для управления расписанием
        keyboard = [
            [InlineKeyboardButton("➕ Добавить рабочие дни", callback_data="add_working_days")],
            [InlineKeyboardButton("📚 Добавить день самообучения", callback_data="add_learning_day")],
            [InlineKeyboardButton("❌ Отметить выходной", callback_data="add_day_off")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(message, reply_markup=reply_markup)

    async def _show_client_schedule(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показывает доступное расписание для клиента"""
        # Получаем расписание на следующие 7 дней
        today = datetime.now().date()
        schedule = self.session.query(Schedule).filter(
            Schedule.date >= today,
            Schedule.date <= today + timedelta(days=7),
            Schedule.is_working_day == True,
            Schedule.is_self_learning == False
        ).all()

        if not schedule:
            await update.message.reply_text("К сожалению, на ближайшую неделю нет свободных дней для записи.")
            return

        # Получаем все существующие записи
        appointments = self.session.query(Appointment).filter(
            Appointment.appointment_time >= today,
            Appointment.is_cancelled == False
        ).all()

        # Формируем сообщение с доступным временем
        message = "📅 Доступное время для записи:\n\n"
        keyboard = []

        for day in schedule:
            # Проверяем доступное время для каждого дня
            available_times = self._get_available_times(day.date, appointments)
            if available_times:
                message += f"\n{day.date.strftime('%d.%m.%Y')}:\n"
                for time in available_times:
                    message += f"🕐 {time.strftime('%H:%M')}\n"
                    keyboard.append([InlineKeyboardButton(
                        f"{day.date.strftime('%d.%m')} {time.strftime('%H:%M')}",
                        callback_data=f"book_{day.date.strftime('%Y-%m-%d')}_{time.strftime('%H-%M')}"
                    )])

        if not keyboard:
            await update.message.reply_text("К сожалению, на ближайшую неделю нет свободного времени для записи.")
            return

        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(message, reply_markup=reply_markup)

    def _get_available_times(self, date: datetime, appointments: List[Appointment]) -> List[datetime]:
        """Возвращает список доступного времени для записи"""
        # Стандартные часы работы: с 9:00 до 18:00
        start_time = datetime.combine(date, datetime.strptime("09:00", "%H:%M").time())
        end_time = datetime.combine(date, datetime.strptime("18:00", "%H:%M").time())
        
        # Создаем список всех возможных времен с интервалом в 1 час
        available_times = []
        current_time = start_time
        while current_time < end_time:
            # Проверяем, не занято ли это время
            is_available = True
            for appointment in appointments:
                if appointment.appointment_time.date() == date and \
                   appointment.appointment_time.hour == current_time.hour:
                    is_available = False
                    break
            
            if is_available:
                available_times.append(current_time)
            
            current_time += timedelta(hours=1)
        
        return available_times

    def add_working_days(self, start_date: datetime, end_date: datetime):
        """Добавляет рабочие дни в расписание"""
        current_date = start_date
        while current_date <= end_date:
            schedule = Schedule(
                date=current_date,
                is_working_day=True,
                is_self_learning=False
            )
            self.session.add(schedule)
            current_date += timedelta(days=1)
        self.session.commit()

    def add_learning_day(self, date: datetime):
        """Добавляет день самообучения"""
        schedule = Schedule(
            date=date,
            is_working_day=False,
            is_self_learning=True
        )
        self.session.add(schedule)
        self.session.commit()

    def add_day_off(self, date: datetime):
        """Добавляет выходной день"""
        schedule = Schedule(
            date=date,
            is_working_day=False,
            is_self_learning=False
        )
        self.session.add(schedule)
        self.session.commit() 
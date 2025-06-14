import os
from pathlib import Path

# Базовые настройки
BASE_DIR = Path(__file__).resolve().parent

# Настройки бота
BOT_TOKEN = "8097150447:AAF9Sqa1X_asFLtY9l5BE_fA9dC6GBk9uFM"
ADMIN_ID = 5147605236

# Настройки базы данных
DATABASE_URL = f"sqlite:///{BASE_DIR}/podiatrist_bot.db"

# Настройки директорий
PHOTOS_DIR = BASE_DIR / "photos"
os.makedirs(PHOTOS_DIR, exist_ok=True)

# Настройки расписания
WORK_START_TIME = "09:00"
WORK_END_TIME = "19:00"
LUNCH_START_TIME = "13:00"
LUNCH_END_TIME = "14:00"
OPTIONAL_WORK_START_TIME = "10:00"
OPTIONAL_WORK_END_TIME = "16:00"

# Настройки логирования
LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
LOG_LEVEL = 'INFO'
LOG_FILE = BASE_DIR / "bot.log"

# Настройки приложения
APPOINTMENT_DURATION = 30  # длительность приема в минутах
SCHEDULE_DAYS_AHEAD = 10  # количество дней для отображения расписания 
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Float, ForeignKey, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from config import DATABASE_URL

# Создаем базовый класс для моделей
Base = declarative_base()

# Создаем движок базы данных
engine = create_engine(DATABASE_URL)

# Модели базы данных
class Client(Base):
    """Модель клиента"""
    __tablename__ = 'clients'
    
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    phone = Column(String, nullable=False)
    problem_description = Column(String)  # Описание проблемы
    photo_path = Column(String)
    appointments = relationship("Appointment", back_populates="client")  # Связь с записями

class Appointment(Base):
    """Модель записи на прием"""
    __tablename__ = 'appointments'
    
    id = Column(Integer, primary_key=True)
    client_id = Column(Integer, ForeignKey('clients.id'))  # ID клиента
    date = Column(DateTime, nullable=False)
    time = Column(DateTime, nullable=False)
    is_cancelled = Column(Boolean, default=False)  # Статус отмены
    client = relationship("Client", back_populates="appointments")  # Связь с клиентом

class Schedule(Base):
    """Модель расписания"""
    __tablename__ = 'schedule'
    
    id = Column(Integer, primary_key=True)
    date = Column(DateTime, nullable=False)
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=False)
    is_working_day = Column(Boolean, default=True)  # Рабочий день

# Создаем все таблицы
Base.metadata.create_all(engine) 
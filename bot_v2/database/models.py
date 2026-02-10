import datetime
from sqlalchemy import (
    Column,
    Integer,
    BigInteger,
    String,
    Float,
    Boolean,
    DateTime,
    Date,
    Time,
    ForeignKey,
    JSON,
    Table,
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

tariff_questionnaires_table = Table('tariff_questionnaires', Base.metadata,
    Column('tariff_id', Integer, ForeignKey('tariffs.id'), primary_key=True),
    Column('questionnaire_id', Integer, ForeignKey('questionnaires.id'), primary_key=True)
)


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    telegram_id = Column(BigInteger, unique=True, nullable=False)
    username = Column(String, nullable=True)
    tariff_id = Column(Integer, ForeignKey("tariffs.id"), nullable=True)
    has_paid = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    tariff = relationship("Tariff", back_populates="users")


class Tariff(Base):
    __tablename__ = "tariffs"
    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=False)
    description = Column(String)
    price = Column(Float, nullable=False)
    users = relationship("User", back_populates="tariff")
    questionnaires = relationship(
        "Questionnaire",
        secondary=tariff_questionnaires_table,
        back_populates="tariffs")


class Payment(Base):
    __tablename__ = "payments"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    amount = Column(Float, nullable=False)
    status = Column(String, nullable=False)
    provider_charge_id = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    user = relationship("User", back_populates="payments")


User.payments = relationship("Payment", order_by=Payment.id, back_populates="user")


class Questionnaire(Base):
    __tablename__ = "questionnaires"
    id = Column(Integer, primary_key=True)
    title = Column(String, nullable=False, unique=True)
    tariffs = relationship(
        "Tariff",
        secondary=tariff_questionnaires_table,
        back_populates="questionnaires")


class Question(Base):
    __tablename__ = "questions"
    id = Column(Integer, primary_key=True)
    questionnaire_id = Column(Integer, ForeignKey("questionnaires.id"), nullable=False)
    text = Column(String, nullable=False)
    type = Column(String, nullable=False)
    options = Column(JSON, nullable=True)
    questionnaire = relationship("Questionnaire", back_populates="questions")
    logic_rules = relationship("QuestionLogic", back_populates="question", foreign_keys="[QuestionLogic.question_id]")


Questionnaire.questions = relationship(
    "Question", order_by=Question.id, back_populates="questionnaire"
)


class QuestionLogic(Base):
    __tablename__ = "question_logic"
    id = Column(Integer, primary_key=True)
    question_id = Column(Integer, ForeignKey("questions.id"), nullable=False)
    answer_value = Column(String, nullable=False)
    next_question_id = Column(Integer, ForeignKey("questions.id"), nullable=True)
    question = relationship("Question", back_populates="logic_rules", foreign_keys=[question_id])


class Answer(Base):
    __tablename__ = "answers"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    question_id = Column(Integer, ForeignKey("questions.id"), nullable=False)
    answer_text = Column(String)
    photo_file_id = Column(String)
    user = relationship("User", back_populates="answers")
    question = relationship("Question", back_populates="answers")


User.answers = relationship("Answer", order_by=Answer.id, back_populates="user")
Question.answers = relationship("Answer", order_by=Answer.id, back_populates="question")


class TimeSlot(Base):
    __tablename__ = "time_slots"
    id = Column(Integer, primary_key=True)
    date = Column(Date, nullable=False)
    time = Column(Time, nullable=False)
    is_available = Column(Boolean, default=True)


class Booking(Base):
    __tablename__ = "bookings"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    slot_id = Column(Integer, ForeignKey("time_slots.id"), nullable=False)
    status = Column(String, nullable=False)
    user = relationship("User", back_populates="bookings")
    slot = relationship("TimeSlot", back_populates="bookings")


User.bookings = relationship("Booking", order_by=Booking.id, back_populates="user")
TimeSlot.bookings = relationship(
    "Booking", order_by=Booking.id, back_populates="slot"
)

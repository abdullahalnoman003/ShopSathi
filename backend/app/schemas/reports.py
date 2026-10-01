from datetime import date, datetime

from pydantic import BaseModel


class ReportSummary(BaseModel):
    from_date: date
    to_date: date
    messages_handled_by_ai: int  # AI replies successfully sent on Messenger
    chats_handed_to_humans: int  # distinct Messenger chats the AI handed over
    orders_drafted: int
    orders_confirmed: int


class InsightQuestion(BaseModel):
    question: str
    count: int  # approximate: the number of customer messages that asked it


class InsightProduct(BaseModel):
    name: str
    count: int


class WeeklyInsightOut(BaseModel):
    week_start: date  # Monday (Asia/Dhaka)
    week_end: date  # Sunday
    generated_at: datetime
    top_questions: list[InsightQuestion]  # at most 5, most asked first
    missing_products: list[InsightProduct]  # asked for, not in the catalogue, most asked first


class WeeklyInsightWeek(BaseModel):
    week_start: date
    week_end: date
    generated_at: datetime

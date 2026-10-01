from datetime import date

from pydantic import BaseModel


class ReportSummary(BaseModel):
    from_date: date
    to_date: date
    messages_handled_by_ai: int  # AI replies successfully sent on Messenger
    chats_handed_to_humans: int  # distinct Messenger chats the AI handed over
    orders_drafted: int
    orders_confirmed: int

from datetime import datetime

from pydantic import BaseModel, Field


class ConnectUrlOut(BaseModel):
    url: str


class AvailablePageOut(BaseModel):
    id: str
    name: str
    in_use: bool  # already connected to a shop (this one or another): cannot be picked


class ConnectPageIn(BaseModel):
    page_id: str = Field(min_length=1, max_length=64)


class ConnectedPageOut(BaseModel):
    id: str  # the Facebook Page id
    name: str
    connected_at: datetime


class PageStatusOut(BaseModel):
    connected: bool
    page: ConnectedPageOut | None = None  # never contains the Page token


class DisconnectOut(BaseModel):
    disconnected: bool

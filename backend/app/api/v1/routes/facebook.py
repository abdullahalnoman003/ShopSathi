from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.api.deps import get_current_shop_id, require_owner
from app.core.database import get_db
from app.models import FacebookPage, User
from app.schemas.facebook import (
    AvailablePageOut,
    ConnectedPageOut,
    ConnectPageIn,
    ConnectUrlOut,
    DisconnectOut,
    PageStatusOut,
)
from app.services.facebook import FacebookError, FacebookService

router = APIRouter(prefix="/facebook", tags=["facebook"])


def get_service(db: Session = Depends(get_db)) -> FacebookService:
    return FacebookService(db)


def _http(e: FacebookError) -> HTTPException:
    return HTTPException(e.status_code, e.message)


def _page_out(row: FacebookPage) -> ConnectedPageOut:
    return ConnectedPageOut(id=row.page_id, name=row.page_name, connected_at=row.connected_at)


@router.get("/connect-url", response_model=ConnectUrlOut)
def connect_url(
    user: User = Depends(require_owner),
    shop_id: int = Depends(get_current_shop_id),
    svc: FacebookService = Depends(get_service),
):
    """The Facebook Login URL for this shop (the `state` is signed, expires, and works once)."""
    try:
        return ConnectUrlOut(url=svc.connect_url(shop_id, user.id))
    except FacebookError as e:
        raise _http(e)


@router.get("/callback", include_in_schema=False)
def callback(
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    svc: FacebookService = Depends(get_service),
):
    """Facebook sends the owner's browser here. There is no login header on this request: the signed `state`
    identifies the shop. Always answers with a redirect to the frontend ("?status=select" or "?error=<code>")."""
    return RedirectResponse(svc.handle_callback(code=code, state=state, error=error), status_code=302)


@router.get("/pages/available", response_model=list[AvailablePageOut])
def available_pages(
    _: User = Depends(require_owner),
    shop_id: int = Depends(get_current_shop_id),
    svc: FacebookService = Depends(get_service),
):
    try:
        return svc.available_pages(shop_id)
    except FacebookError as e:
        raise _http(e)


@router.post("/pages/connect", response_model=ConnectedPageOut)
def connect_page(
    body: ConnectPageIn,
    _: User = Depends(require_owner),
    shop_id: int = Depends(get_current_shop_id),
    svc: FacebookService = Depends(get_service),
):
    try:
        return _page_out(svc.connect(shop_id, body.page_id))
    except FacebookError as e:
        raise _http(e)


@router.get("/page", response_model=PageStatusOut)
def page_status(
    _: User = Depends(require_owner),
    shop_id: int = Depends(get_current_shop_id),
    svc: FacebookService = Depends(get_service),
):
    row = svc.get_page(shop_id)
    return PageStatusOut(connected=row is not None, page=_page_out(row) if row else None)


@router.post("/page/disconnect", response_model=DisconnectOut)
def disconnect_page(
    _: User = Depends(require_owner),
    shop_id: int = Depends(get_current_shop_id),
    svc: FacebookService = Depends(get_service),
):
    try:
        svc.disconnect(shop_id)
    except FacebookError as e:
        raise _http(e)
    return DisconnectOut(disconnected=True)

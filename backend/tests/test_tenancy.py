from fastapi import Depends, FastAPI
from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.api.deps import get_current_shop_id, require_roles
from app.core.database import Base, engine, get_db
from app.main import app
from app.services.tenant import ShopScopedRepository
from tests.conftest import auth_header


class Note(Base):
    """Throwaway shop-owned table used only to prove the tenant-scoping helper."""

    __tablename__ = "test_notes"
    id: Mapped[int] = mapped_column(primary_key=True)
    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id", ondelete="CASCADE"), index=True)
    text: Mapped[str] = mapped_column(String(100))


class NoteRepo(ShopScopedRepository[Note]):
    model = Note


def test_user_of_shop_a_cannot_read_shop_b_data(signup, db):
    a = signup(shop="Shop A", email="a@example.com").json()["shop"]["id"]
    b = signup(shop="Shop B", email="b@example.com").json()["shop"]["id"]
    Note.__table__.create(engine, checkfirst=True)
    try:
        note_a = NoteRepo(db, a).add(Note(text="a-secret"))
        note_b = NoteRepo(db, b).add(Note(text="b-secret"))
        db.commit()

        repo_a = NoteRepo(db, a)
        assert [n.text for n in repo_a.list()] == ["a-secret"]
        assert repo_a.get(note_a.id) is not None
        assert repo_a.get(note_b.id) is None  # B's row is invisible to A even by id
    finally:
        db.close()
        Note.__table__.drop(engine, checkfirst=True)


def test_shop_id_comes_from_token_only(signup, client):
    @app.get("/_test/shop-id")
    def shop_id_route(shop_id: int = Depends(get_current_shop_id)):
        return {"shop_id": shop_id}

    @app.get("/_test/admin-only", dependencies=[Depends(require_roles("platform_admin"))])
    def admin_route():
        return {"ok": True}

    try:
        a = signup(shop="Shop A", email="a@example.com").json()
        signup(shop="Shop B", email="b@example.com")
        h = auth_header(a["access_token"])
        # a client-supplied shop_id is ignored
        r = client.get("/_test/shop-id", params={"shop_id": 999}, headers=h)
        assert r.json() == {"shop_id": a["shop"]["id"]}
        assert client.get("/_test/shop-id").status_code == 401
        assert client.get("/_test/admin-only", headers=h).status_code == 403
    finally:
        app.router.routes[:] = [r for r in app.router.routes if not getattr(r, "path", "").startswith("/_test")]

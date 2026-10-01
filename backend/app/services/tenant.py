"""Tenant scoping (FR-02): every shop-owned query goes through here, filtered by shop_id."""

from typing import Any, Generic, TypeVar

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

T = TypeVar("T")


def scoped_select(model: type[T], shop_id: int) -> Select[tuple[T]]:
    """A SELECT on a shop-owned model that is already filtered by shop_id."""
    return select(model).where(model.shop_id == shop_id)  # type: ignore[attr-defined]


class ShopScopedRepository(Generic[T]):
    """Base repository for shop-owned tables.

    shop_id comes from the get_current_shop_id dependency, never from the client.
    """

    model: type[T]

    def __init__(self, db: Session, shop_id: int) -> None:
        self.db = db
        self.shop_id = shop_id

    def query(self) -> Select[tuple[T]]:
        return scoped_select(self.model, self.shop_id)

    def get(self, obj_id: int) -> T | None:
        model: Any = self.model
        return self.db.scalars(self.query().where(model.id == obj_id)).first()

    def list(self) -> list[T]:
        return list(self.db.scalars(self.query()))

    def add(self, obj: T) -> T:
        o: Any = obj
        o.shop_id = self.shop_id
        self.db.add(obj)
        self.db.flush()
        return obj

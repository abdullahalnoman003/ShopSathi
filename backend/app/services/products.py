"""Product catalogue service. Every query is scoped to the shop (FR-02)."""

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Product
from app.services.storage import StorageService
from app.services.tenant import ShopScopedRepository

MAX_PHOTOS = 5


class ProductHooks:
    """HOOK POINT for Prompt 8 (embeddings): called after a product is created, updated, or had photos
    changed (`product_changed`) and after it is deleted (`product_deleted`).

    Both are no-ops now. Prompt 8 replaces/extends them to refresh or remove the product's embedding.
    """

    def product_changed(self, shop_id: int, product_id: int) -> None:
        pass

    def product_deleted(self, shop_id: int, product_id: int) -> None:
        pass


product_hooks = ProductHooks()


class PhotoLimitError(ValueError):
    pass


class ProductService(ShopScopedRepository[Product]):
    model = Product

    def __init__(self, db: Session, shop_id: int, storage: StorageService | None = None) -> None:
        super().__init__(db, shop_id)
        self.storage = storage or StorageService()

    def search(self, q: str | None, page: int, page_size: int) -> tuple[list[Product], int]:
        query = self.query()
        if q:
            escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            query = query.where(Product.name.ilike(f"%{escaped}%", escape="\\"))
        total = self.db.scalar(select(func.count()).select_from(query.subquery())) or 0
        items = self.db.scalars(
            query.order_by(Product.id.desc()).offset((page - 1) * page_size).limit(page_size)
        )
        return list(items), total

    def create(self, photos: list[str] | None = None, **fields: Any) -> Product:
        """Create a product (also used by the CSV/Excel import; `photos` are storage keys or external URLs)."""
        product = self.add(Product(photos=photos or [], **fields))
        self.db.commit()
        product_hooks.product_changed(self.shop_id, product.id)
        return product

    def update(self, product: Product, **fields: Any) -> Product:
        for key, value in fields.items():
            setattr(product, key, value)
        self.db.commit()
        product_hooks.product_changed(self.shop_id, product.id)
        return product

    def delete(self, product: Product) -> None:
        keys, product_id = list(product.photos), product.id
        self.db.delete(product)
        self.db.commit()
        for key in keys:
            self.storage.delete(key)
        product_hooks.product_deleted(self.shop_id, product_id)

    def add_photos(self, product: Product, files: list[bytes]) -> Product:
        """All-or-nothing: every file is validated before anything is stored."""
        if len(product.photos) + len(files) > MAX_PHOTOS:
            raise PhotoLimitError(f"A product can have at most {MAX_PHOTOS} photos")
        extensions = [self.storage.validate(data) for data in files]
        new_keys = [self.storage.save(self.shop_id, d, e) for d, e in zip(files, extensions)]
        product.photos = [*product.photos, *new_keys]
        self.db.commit()
        product_hooks.product_changed(self.shop_id, product.id)
        return product

    def remove_photo(self, product: Product, index: int) -> Product:
        key = product.photos[index]
        product.photos = [k for i, k in enumerate(product.photos) if i != index]
        self.db.commit()
        self.storage.delete(key)
        product_hooks.product_changed(self.shop_id, product.id)
        return product


from fastapi import APIRouter, Response, Depends, HTTPException, Query, UploadFile, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_shop_id, require_owner
from app.core.database import get_db
from app.models import Product
from app.core.config import get_settings
from app.schemas.products import ImportResult, ProductIn, ProductOut, ProductPage
from app.services.product_import import TEMPLATE_CSV, ImportFileError, import_rows, parse_file
from app.services.products import PhotoLimitError, ProductService
from app.services.storage import InvalidImage, StorageService

# Owner only (access matrix). The shop always comes from the token via get_current_shop_id.
router = APIRouter(prefix="/products", tags=["products"], dependencies=[Depends(require_owner)])


def get_service(shop_id: int = Depends(get_current_shop_id), db: Session = Depends(get_db)) -> ProductService:
    return ProductService(db, shop_id)


def to_out(p: Product, storage: StorageService) -> ProductOut:
    return ProductOut(
        id=p.id,
        name=p.name,
        description=p.description,
        price=p.price,
        sizes=p.sizes,
        colours=p.colours,
        stock_count=p.stock_count,
        photos=[storage.url(k) for k in p.photos],
        created_at=p.created_at,
        updated_at=p.updated_at,
    )


def _get_or_404(svc: ProductService, product_id: int) -> Product:
    product = svc.get(product_id)
    if product is None:  # also hides other shops' products
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Product not found")
    return product


@router.get("", response_model=ProductPage)
def list_products(
    q: str | None = Query(default=None, max_length=100),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    svc: ProductService = Depends(get_service),
):
    items, total = svc.search(q, page, page_size)
    return ProductPage(items=[to_out(p, svc.storage) for p in items], total=total, page=page, page_size=page_size)


@router.post("", response_model=ProductOut, status_code=status.HTTP_201_CREATED)
def create_product(body: ProductIn, svc: ProductService = Depends(get_service)):
    return to_out(svc.create(**body.model_dump()), svc.storage)


# Import routes come before /{product_id} so "import" is never read as an id.
@router.get("/import/template")
def import_template():
    return Response(
        TEMPLATE_CSV,
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="products_template.csv"'},
    )


@router.post("/import", response_model=ImportResult)
async def import_products(file: UploadFile, svc: ProductService = Depends(get_service)):
    """Bulk-create products from a .csv or .xlsx file; invalid rows are skipped and reported."""
    limit = get_settings().max_import_mb * 1024 * 1024
    data = await file.read(limit + 1)
    try:
        rows = parse_file(file.filename or "", data)
    except ImportFileError as e:
        raise HTTPException(e.status_code, e.message)
    return import_rows(svc, rows)


@router.get("/{product_id}", response_model=ProductOut)
def get_product(product_id: int, svc: ProductService = Depends(get_service)):
    return to_out(_get_or_404(svc, product_id), svc.storage)


@router.put("/{product_id}", response_model=ProductOut)
def update_product(product_id: int, body: ProductIn, svc: ProductService = Depends(get_service)):
    product = _get_or_404(svc, product_id)
    return to_out(svc.update(product, **body.model_dump()), svc.storage)


@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_product(product_id: int, svc: ProductService = Depends(get_service)):
    svc.delete(_get_or_404(svc, product_id))


@router.post("/{product_id}/photos", response_model=ProductOut)
async def upload_photos(product_id: int, files: list[UploadFile], svc: ProductService = Depends(get_service)):
    product = _get_or_404(svc, product_id)
    max_bytes = svc.storage.max_bytes
    contents: list[bytes] = []
    for f in files:
        data = await f.read(max_bytes + 1)  # never read more than the limit allows
        contents.append(data)
    try:
        svc.add_photos(product, contents)
    except (PhotoLimitError, InvalidImage) as e:
        raise HTTPException(422, str(e))
    return to_out(product, svc.storage)


@router.delete("/{product_id}/photos/{index}", response_model=ProductOut)
def remove_photo(product_id: int, index: int, svc: ProductService = Depends(get_service)):
    product = _get_or_404(svc, product_id)
    if not 0 <= index < len(product.photos):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Photo not found")
    return to_out(svc.remove_photo(product, index), svc.storage)

"""Shop policy (FR-06). Every query is scoped to the shop (FR-02)."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.models import DeliveryArea, ShopPolicy
from app.schemas.policy import PolicyIn
from app.services.policy_text import normalise_area
from app.services.tenant import scoped_select


class PolicyHooks:
    """`policy_changed` is called after a shop's policy is saved. It queues the job that re-embeds the
    shop's policy chunks (Prompt 8). Queueing never fails the request.
    """

    def policy_changed(self, shop_id: int) -> None:
        from app.workers.dispatch import enqueue
        from app.workers.tasks import embed_policy

        enqueue(embed_policy, shop_id)


policy_hooks = PolicyHooks()


@dataclass(frozen=True)
class PolicyData:
    delivery_time: str
    return_rules: str
    payment_options: str
    delivery_areas: list[tuple[str, Decimal]]
    updated_at: datetime | None


@dataclass(frozen=True)
class DeliveryCharge:
    """Result of a delivery-charge lookup. `found` is False when the shop has no such area."""

    found: bool
    area_name: str | None = None
    charge: Decimal | None = None


class PolicyService:
    def __init__(self, db: Session, shop_id: int) -> None:
        self.db = db
        self.shop_id = shop_id

    def _areas(self) -> list[DeliveryArea]:
        return list(self.db.scalars(scoped_select(DeliveryArea, self.shop_id).order_by(DeliveryArea.id)))

    def get(self) -> PolicyData:
        """The shop's policy, or empty defaults if it has not been saved yet."""
        policy = self.db.scalars(scoped_select(ShopPolicy, self.shop_id)).first()
        return PolicyData(
            delivery_time=policy.delivery_time if policy else "",
            return_rules=policy.return_rules if policy else "",
            payment_options=policy.payment_options if policy else "",
            delivery_areas=[(a.area_name, a.charge) for a in self._areas()],
            updated_at=policy.updated_at if policy else None,
        )

    def save(self, data: PolicyIn) -> PolicyData:
        """Replace the whole policy, including the delivery areas list."""
        policy = self.db.scalars(scoped_select(ShopPolicy, self.shop_id)).first()
        if policy is None:
            policy = ShopPolicy(shop_id=self.shop_id)
            self.db.add(policy)
        policy.delivery_time = data.delivery_time
        policy.return_rules = data.return_rules
        policy.payment_options = data.payment_options
        self.db.execute(delete(DeliveryArea).where(DeliveryArea.shop_id == self.shop_id))
        self.db.add_all(
            DeliveryArea(shop_id=self.shop_id, area_name=a.area_name, charge=a.charge) for a in data.delivery_areas
        )
        self.db.commit()
        policy_hooks.policy_changed(self.shop_id)
        return self.get()

    def get_delivery_charge(self, area_text: str) -> DeliveryCharge:
        """Look up the charge for an area by case-insensitive / normalised exact match.

        No guessing: partial or fuzzy matches ("Khag", "Khagan e") are NOT found. Prompt 9's AI tool
        extracts the area name from the customer's message and calls this.
        """
        wanted = normalise_area(area_text or "")
        if not wanted:
            return DeliveryCharge(found=False)
        for area in self._areas():
            if normalise_area(area.area_name) == wanted:
                return DeliveryCharge(found=True, area_name=area.area_name, charge=area.charge)
        return DeliveryCharge(found=False)

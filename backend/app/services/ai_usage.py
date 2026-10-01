"""Per-shop AI usage and cost logging (NFR-08). Reused by every AI feature."""

from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import AiUsageLog


def estimate_cost(model: str, input_tokens: int, output_tokens: int = 0) -> Decimal:
    """USD estimate from the per-model rates in config (unknown models cost 0 and are still logged)."""
    rates = get_settings().ai_cost_rates.get(model, {})
    cost = (
        Decimal(str(rates.get("input_per_1m", 0))) * input_tokens
        + Decimal(str(rates.get("output_per_1m", 0))) * output_tokens
    ) / Decimal(1_000_000)
    return cost.quantize(Decimal("0.000001"))


def log_ai_usage(
    db: Session,
    shop_id: int,
    operation: str,
    provider: str,
    model: str,
    input_tokens: int,
    output_tokens: int = 0,
) -> AiUsageLog:
    row = AiUsageLog(
        shop_id=shop_id,
        operation=operation,
        provider=provider,
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        estimated_cost=estimate_cost(model, input_tokens, output_tokens),
    )
    db.add(row)
    db.commit()
    return row

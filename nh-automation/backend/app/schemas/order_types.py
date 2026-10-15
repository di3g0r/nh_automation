"""Order literals shared by app.schemas.orders and app.schemas.production."""

from __future__ import annotations

from typing import Literal

OrderType = Literal["trabajo", "retrabajo"]
OrderStatus = Literal[
    "created", "assigned", "in_progress", "paused", "completed", "closed", "cancelled"
]

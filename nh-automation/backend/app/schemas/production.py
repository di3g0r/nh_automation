"""Phase 3 schemas: expiry, machine assignments, production controls,
traceability, closing, Producción lists and the machine board."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field

from app.schemas.order_types import OrderStatus, OrderType

AssignmentStatus = Literal["pending", "running", "paused", "completed", "cancelled"]
Source = Literal["plc", "manual"]
MachineState = Literal["free", "busy", "paused", "maintenance"]
ChecklistItem = Literal["lote_etiqueta", "niveles_producto", "cantidades", "embalaje"]
# What still blocks an order in "Por asignar" (FR-PM-1).
MissingForAssign = Literal["expiry", "machines"]
# What is incomplete when closing (the dialog lists it, never blocks; BR-11).
MissingForClose = Literal["checklist", "new_lot", "materials", "labels"]


def _strip_or_none(v):  # type: ignore[no-untyped-def]
    if isinstance(v, str):
        v = v.strip()
    return v or None


OptionalText = Annotated[str | None, BeforeValidator(_strip_or_none)]


# Input ------------------------------------------------------------------------


class ExpiryIn(BaseModel):
    """Any day of the month is accepted; it is stored as the 1st (OPEN-4).
    `null` clears a Trabajo expiry (the order returns to Creada)."""

    model_config = ConfigDict(extra="forbid")
    expiry_date: date | None


class AssignmentIn(BaseModel):
    machine_id: int
    planned_liters: Decimal = Field(gt=0, max_digits=12, decimal_places=2)


class AssignmentsIn(BaseModel):
    """Replaces the whole split. An empty list removes every assignment."""

    model_config = ConfigDict(extra="forbid")
    assignments: list[AssignmentIn]


class QueuePositionIn(BaseModel):
    queue_position: int = Field(ge=1)  # 1 = next on the machine


class CompleteIn(BaseModel):
    actual_liters: Decimal = Field(ge=0, max_digits=12, decimal_places=2)


class ChecklistEntryIn(BaseModel):
    item: ChecklistItem
    checked: bool


class ChecklistIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[ChecklistEntryIn] = Field(min_length=1)


class TraceabilityIn(BaseModel):
    """PATCH: only sent fields change. TODO(OPEN-4): lot format; free text."""

    model_config = ConfigDict(extra="forbid")
    new_lot: OptionalText = Field(default=None, max_length=100)
    previous_lot: OptionalText = Field(default=None, max_length=100)


class MaterialActualIn(BaseModel):
    packaging_item_id: int
    actual_qty: int | None = Field(ge=0)  # null clears it (the planned quantity applies)


class MaterialsIn(BaseModel):
    """PATCH: only sent rows / fields change."""

    model_config = ConfigDict(extra="forbid")
    packaging: list[MaterialActualIn] = Field(default_factory=list)
    labels_actual: int | None = Field(default=None, ge=0)


class CloseIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    note: OptionalText = Field(default=None, max_length=2000)


# Output -----------------------------------------------------------------------


class AssignmentOut(BaseModel):
    id: int
    order_id: int
    operation_number: str
    order_type: OrderType
    order_status: OrderStatus
    finished_code: str
    finished_name: str
    machine_id: int
    machine_code: str
    machine_name: str
    planned_liters: Decimal
    actual_liters: Decimal | None
    status: AssignmentStatus
    queue_position: int
    last_source: Source | None
    assigned_by_name: str
    assigned_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    # Allowed actions right now (status + machine queue, BR-14/20). The UI also
    # checks production.control; the API enforces it.
    can_start: bool
    can_pause: bool
    can_resume: bool
    can_complete: bool
    # Why a pending assignment cannot start yet (Spanish), or None.
    start_blocked_reason: str | None


class DifferenceOut(BaseModel):
    """BR-12. Negative = Faltante, positive = Excedente."""

    ordered_liters: Decimal
    actual_liters: Decimal
    difference: Decimal
    within_range: bool


class ProductionOrder(BaseModel):
    """One row of a Producción section (FR-PM-1)."""

    id: int
    operation_number: str
    order_type: OrderType
    status: OrderStatus
    client_name: str | None
    razon_social_code: str
    finished_code: str
    finished_name: str
    finished_liters: Decimal
    expiry_date: date | None
    created_at: datetime
    missing: list[MissingForAssign]
    assigned_liters: Decimal
    assignments: list[AssignmentOut]
    difference: DifferenceOut | None  # only once production ended


class MachineBoardItem(BaseModel):
    id: int
    code: str
    name: str
    site_name: str
    in_maintenance: bool
    state: MachineState
    current: AssignmentOut | None  # running or paused assignment
    queue_length: int  # pending assignments
    next_assignment: AssignmentOut | None  # first ready pending, if any


class MachineQueueOut(BaseModel):
    machine_id: int
    machine_code: str
    state: MachineState
    current: AssignmentOut | None
    pending: list[AssignmentOut]  # by queue_position

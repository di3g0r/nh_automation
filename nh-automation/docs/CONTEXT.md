# Project Context: Work Order and Production Tracking System

> Status: Draft v1 — 2026-10-06
> This document describes the business, the problem, and the decisions made so far. It is the base for the Specifications and Requirements documents. Items marked **[OPEN]** are not decided yet.

---

## 1. The business

The company sells fertilizers and other liquid agricultural products. Production work happens in a plant with filling machines; an office right next to the plant handles orders. The main site is **ECOINDUSTRIAL PACÍFICO**, and there are other sites.

Clients (for example NOBELTECH and AGRONB) call the office to order product. The office then creates an internal **work order** (*orden de trabajo*) telling the plant what to do: take a product in one presentation (for example a 1,000 L tote of a base product), pour it into new containers, label it, and produce the finished product the client ordered.

## 2. Current process

1. A client calls and orders a quantity of a product.
2. An office worker prints a blank work order form and fills it in by hand.
3. The worker walks the form to a machine operator.
4. The operator fills the order on a machine (pours product into containers they handle manually, labels them, fills the checklist).
5. The operator walks back to tell the office it is done.
6. The paper form is signed by the requester, the office approver, the warehouse supervisor and the responsible operator.

## 3. Problems to solve

| Problem | Cause | How the system solves it |
|---|---|---|
| Slow process | Paper forms carried by hand both ways | Orders created and assigned on screen; operators see them at their station |
| Communication mistakes | Handwritten data, verbal status updates | Structured fields, catalogs, statuses reported by the system and the PLC |
| Overselling | No visibility of product already committed to orders in progress | Inventory is reserved when an order is created; an order cannot be created if available stock is insufficient |

## 4. Goals

- Replace paper work orders with digital ones (labels will still be printed).
- Let admins see which machines and operators are free and assign orders to them.
- Let operators see their assigned orders and report progress.
- Have machines (PLCs) receive orders and report real production data automatically.
- Keep inventory (products and packaging materials) in a database, replacing spreadsheets.
- Prevent creating orders for stock that is already committed.
- Later: a dashboard of daily production by machine, operator, product, etc.

## 5. Scope

**First version (focus)**
- User management (CRUD) with roles.
- Work order management (CRUD) with the full lifecycle and approvals.
- Product catalog and packaging material catalog.
- Inventory with reservation.
- Machine registry and assignment of orders to machine + operator.
- Operator view of assigned orders.
- Own API used by the web app and by the PLCs.
- Two-way PLC integration (see §9).

**Later**
- Production dashboard (by day, machine, operator, product).
- Label and barcode printing integration **[OPEN]**.

**Out of scope**
- Client management (CRM), sales, invoicing and accounting. Clients only appear as a name on the order (see §6).

## 6. The work order

Based on the current paper forms (*Orden de Trabajo* and *Orden de Retrabajo*).

**Header**
- Order type: *Trabajo* or *Retrabajo*. A *retrabajo* may be a modification of a previous order **[OPEN: confirm; if so, link it to the original order]**.
- Client (e.g. NOBELTECH, AGRONB).
- Site (*Lugar*), default ECOINDUSTRIAL PACÍFICO.
- Date.
- Operation number (*Número de Operación*), e.g. `447 NB`, `8292 ANB`. **[OPEN: the suffix seems tied to the client; confirm how numbers are generated — automatically per client, or entered manually]**

**Quantitative information**
- **ANTES** (source): product code, name, provider, presentation, quantity.
- **DESPUÉS** (result): product code, name, provider, presentation, quantity.
- One row of each per order. Quantities are in **liters**.
- **Differences** (*Faltante / Excedente*): calculated automatically from the quantity ordered versus the quantity the PLC measured.

**Comments / operation**: free text (e.g. "Cambio de envase", "Cambio de etiqueta", "Vaciar porrón", "Reen #301"). **[OPEN: what "Reen #" codes mean]**

**Packaging and labeling materials**: quantity used of each item from the packaging catalog, plus total labels used. Current list on the form:

| Code | Item | Code | Item |
|---|---|---|---|
| ENVCO01005 | Envase 1 L liso Novapack | CAJ01FP007 | Caja Forcrop 12x1 |
| ENVLI01004 | Envase 1 L corrugado | CAJ05FP006 | Caja Forcrop 4x5 |
| ENVLI20001 | Envase 20 L Fisher | CAJ01BL003 | Caja blanca 12x1 |
| ENVLI05003 | Envase 5 L Fisher | CAJ05BL004 | Caja blanca 4x5 |
| ENVLI25007 | Envase 250 ml liso Novapack | CAJ05BL005 | Caja blanca 0.250 grs |
| ENVCO25006 | Envase 250 ml corrugado | CAJ01AZ002 | Caja azul 12x1 |
| BOLTE20008 | Bolsa termosellada 1 kg | CAJ05AZ001 | Caja azul 4x5 |

The list is not complete; packaging must be a managed catalog.

**Quality checklist** (filled by the operator for now; possibly also the supervisor):
- Revisión de lote y etiqueta
- Revisión de niveles de producto
- Revisión de cantidades
- Embalaje

**Traceability**
- Previous lot (*Lote anterior*) and new lot (*Lote posterior*).
- Expiry date (*Fecha de caducidad*), e.g. `0326/0329` (looks like manufacturing/expiry month-year). Assigned by an admin or supervisor. **[OPEN: exact format, to be shared]**
- Barcode option: 1 barcode per container, or 2 barcodes per box.

**Signatures → system actions** (recorded as user + timestamp):
- Requester (*Solicitante*, office)
- Approval (*Aprobación*, office)
- Warehouse supervisor approval (*Bodega*)
- Responsible operator (*Responsable de la operación*, warehouse)

## 7. Order lifecycle

```
Created → Approved → Assigned → In progress → Completed → Verified
```

- **Created**: an admin enters the order; inventory is reserved.
- **Approved**: office approval.
- **Assigned**: the admin picks a free machine and operator; the order is sent to the PLC.
- **In progress**: started at the machine (reported by the PLC/operator).
- **Completed**: the machine finishes; real quantity recorded; differences calculated.
- **Verified**: warehouse supervisor approval.

Orders can be **partially filled** and **split across machines**. **[OPEN: cancellation — who can cancel, and at which stages; what happens to reserved inventory]**

## 8. Inventory

- Inventory moves from spreadsheets into the system's database.
- Tracked items: **products** (by code and presentation, in liters) and **packaging materials** (containers, boxes, bags, labels).
- Product catalog fields: code, name, provider, presentation. Product codes appear to follow a structure (e.g. `GRN100C1XL20F004`, `QVR200C1XL09M01`) **[OPEN: confirm the structure]**. An existing spreadsheet may be imported **[OPEN: obtain it]**.
- **Reservation rule:** when an order is created, the source product (and packaging) is reserved. *Available = on hand − reserved*. The system blocks creating an order if available stock is insufficient.
- On completion, the real quantities move stock: source product and packaging are consumed, the resulting product is added.
- The system warns when packaging runs low.

## 9. Machines and PLC integration

- Around **6 machines**. Any machine can handle any product.
- Each machine has a **PLC that can make HTTP requests**. **[OPEN: brand/model — being researched; who programs the PLC]**
- Communication is **two-way**:
  - **System → PLC:** the PLC is notified that it has an assigned order (product, quantity).
  - **PLC → System:** the PLC reports status, quantity dispensed and timestamps through our API, which writes to the database.
- The PLC measures the real quantity dispensed; actual versus ordered quantity is recorded.
- **[OPEN: exact mechanism for System → PLC]** — depends on the PLC model (e.g. the PLC polls our API for its next order, or the server pushes to the PLC).
- **[OPEN: what happens if the network or server is down while a machine is working]**

## 10. Users and roles

| Role | Who | Access |
|---|---|---|
| Master admin | Company director | Everything |
| Admin | Office workers | Create and manage work orders, assign machines and operators |
| Operator | Machine operators | See and work on their assigned orders, fill checklist |

**[OPEN: the warehouse supervisor (*Bodega*) approves orders and may fill the checklist. Is that a separate role, or an admin/operator permission?]**

## 11. Architecture and infrastructure

- Web application for admins and the master admin.
- Operator interface **[OPEN: tablet or PC at each machine, phone, or the PLC screen]**.
- Own **API** used by the web app and the PLCs.
- Database for orders, inventory, users, machines and PLC events.
- Hosted on **our own small server** in the office, maintained by an IT person.
- Office and plant are next to each other and on the **same network**.
- Office workers access the program through a **VPN**. **[OPEN: since everything is on the same network, confirm the VPN's purpose — e.g. restricting who can reach the app, or separating the machine/PLC network from the office network]**
- Programming language: no preference.
- **User interface language: Spanish.**

## 12. Decisions made

- Paper work orders are replaced by digital ones; labels are still printed.
- Clients keep ordering by phone; admins create the work orders.
- Inventory moves into the system's database.
- Inventory is reserved at order creation; orders exceeding available stock are blocked.
- Two-way PLC integration through our own API.
- Quantities in liters; one ANTES and one DESPUÉS row per order.
- Comments are free text.
- Packaging materials are tracked as inventory.
- Approvals and verification are lifecycle steps.
- Differences are calculated from PLC measurements.
- Self-hosted server, Spanish UI, roles: master admin, admin, operator.

## 13. Open questions

1. *Trabajo* vs *Retrabajo* — is a retrabajo a modification of a previous order?
2. How operation numbers are generated (per client suffix such as NB / ANB?).
3. Meaning of "Reen #" codes in comments.
4. Lot and expiry date format.
5. Product code structure; product spreadsheet for import.
6. PLC brand/model and who programs it.
7. Mechanism for sending orders to the PLC.
8. Behavior when the network/server is down during production.
9. Operator device.
10. Supervisor role.
11. Order cancellation rules.
12. Label and barcode printing integration.
13. Purpose of the VPN given a shared network.
14. Other sites: do they use this system too?
15. Order volume per day and number of users.

## 14. Glossary

| Spanish | English / meaning |
|---|---|
| Orden de trabajo | Work order |
| Orden de retrabajo | Rework order |
| Antes / Después | Source product / resulting product |
| Presentación | Presentation (container size, e.g. 1x20 = one 20 L container) |
| Envase | Container |
| Porrón | Large drum / tote |
| Caja | Box |
| Etiqueta | Label |
| Lote | Lot / batch |
| Fecha de caducidad | Expiry date |
| Faltante / Excedente | Shortage / surplus |
| Bodega | Warehouse |
| Solicitante | Requester |
| Embalaje | Packing |

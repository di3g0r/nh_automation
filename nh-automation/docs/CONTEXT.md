# Project Context: Work Order and Production Tracking System

> Status: v2 — 2026-10-09 (v1: 2026-10-06)
> This document describes the business, the problem, and the decisions made so far. It is the base for the specifications in `docs/specs/`. Items marked **[OPEN]** are not decided yet.
> v2 changes: razones sociales, several source products per order, two kinds of rework, expiry rules, PLC works directly against the database (PLC programming out of scope), no VPN, inventory imported from an external database, cancellation rules.

---

## 1. The business

The company sells fertilizers and other liquid agricultural products. Production work happens in a plant with filling machines; an office right next to the plant handles orders. The main site is **ECOINDUSTRIAL PACÍFICO**, and there are other sites.

The company operates under several **razones sociales** (legal entities); there are 4 today, for example NOBELTECH (`NB`) and AGRONB (`ANB`). Every product belongs to one razón social.

Clients call the office to order product. The office then creates an internal **work order** (*orden de trabajo*) telling the plant what to do: take one or more products (for example a 1,000 L tote of a base product), pour or mix them into new containers, label them, and produce the finished product the client ordered.

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
| Slow process | Paper forms carried by hand both ways | Orders created and assigned on screen; machines pick them up from the database |
| Communication mistakes | Handwritten data, verbal status updates | Structured fields, catalogs, statuses written by the system and the PLC |
| Overselling | No visibility of product already committed to orders in progress | Inventory is reserved when an order is created; an order cannot be created if available stock is insufficient |

## 4. Goals

- Replace paper work orders with digital ones (labels will still be printed).
- Let admins see which machines and operators are free and assign orders to them.
- Let machines (PLCs) pick up their pending orders and record production progress in the database.
- Keep inventory (products and packaging materials) in the system's database, imported from the company's existing database.
- Prevent creating orders for stock that is already committed.
- Later: a dashboard of daily production by machine, operator, product, etc.

## 5. Scope

**First version (focus)**
- User management (CRUD) with roles.
- Work order management (CRUD) with the full lifecycle and approvals.
- Catalogs: products, packaging materials, razones sociales, clients, sites, machines.
- Inventory with reservation.
- Assignment of orders to machine + operator.
- Operator view of assigned orders (checklist, materials used).
- **Database interface for the PLCs**: where they read pending orders and write their progress (see §9).

**Out of scope**
- **Programming the PLCs.** It is done separately by someone else; we only provide and document the database interface.
- Client management (CRM), sales, invoicing and accounting. Clients only appear as a name on the order.
- VPN. The system is used only from the local network.
- Handling server or network outages (if the server is down, nothing is done).

**Later**
- Production dashboard (by day, machine, operator, product).
- Label and barcode printing integration **[OPEN]**.

## 6. The work order

Based on the current paper forms (*Orden de Trabajo* and *Orden de Retrabajo*).

**Header**
- **Order type:**
  - *Trabajo*: normal work order for a client.
  - *Retrabajo* of a **previous order**: modifies an order that was already made; linked to it.
  - *Retrabajo* of **own stock**: we modify our own product for any reason (damaged container, label change, etc.). Not linked to a previous order and has no client.
- **Client:** required, except for *retrabajo* of own stock.
- **Razón social:** determines the operation number suffix. Defaults to the razón social of the source products; when the order mixes products from different razones sociales, the user chooses which one to use.
- Site (*Lugar*), default ECOINDUSTRIAL PACÍFICO.
- Date.
- **Operation number** (*Número de Operación*), e.g. `447 NB`, `8292 ANB`: a number from a **separate sequence per razón social**, followed by the razón social code. Generated automatically. The current paper numbers are unknown, so each sequence's next number is configurable.

**Quantitative information**
- **ANTES** (source): **one or more** products (several when products are mixed), each with code, name, provider, presentation and quantity.
- **DESPUÉS** (result): one product with code, name, provider, presentation and quantity.
- Quantities are in **liters**.
- **Differences** (*Faltante / Excedente*): calculated automatically from the quantity ordered versus the quantity actually produced.

**Comments / operation**: free text (e.g. "Cambio de envase", "Cambio de etiqueta", "Vaciar porrón", "Reen #301"). **[OPEN: what "Reen #" codes mean]**

**Packaging and labeling materials**: quantity used of each item from the packaging catalog, plus total labels used. Initial list from the form:

| Code | Item | Code | Item |
|---|---|---|---|
| ENVCO01005 | Envase 1 L liso Novapack | CAJ01FP007 | Caja Forcrop 12x1 |
| ENVLI01004 | Envase 1 L corrugado | CAJ05FP006 | Caja Forcrop 4x5 |
| ENVLI20001 | Envase 20 L Fisher | CAJ01BL003 | Caja blanca 12x1 |
| ENVLI05003 | Envase 5 L Fisher | CAJ05BL004 | Caja blanca 4x5 |
| ENVLI25007 | Envase 250 ml liso Novapack | CAJ05BL005 | Caja blanca 0.250 grs |
| ENVCO25006 | Envase 250 ml corrugado | CAJ01AZ002 | Caja azul 12x1 |
| BOLTE20008 | Bolsa termosellada 1 kg | CAJ05AZ001 | Caja azul 4x5 |

The list is not complete; packaging is a managed catalog.

**Quality checklist** (filled by the operator for now; possibly also the supervisor):
- Revisión de lote y etiqueta
- Revisión de niveles de producto
- Revisión de cantidades
- Embalaje

**Traceability**
- Previous lot (*Lote anterior*) and new lot (*Lote posterior*). **[OPEN: lot format]**
- **Expiry date** (*Fecha de caducidad*):
  - *Trabajo*: defaults to **3 years** after the order date; the user can change it.
  - *Retrabajo*: the product **keeps its original expiry**. Rework of a previous order copies that order's expiry; rework of own stock requires the user to enter the original expiry (no default).
  - On the paper form it appears as e.g. `0326/0329` (looks like manufacture/expiry month-year). **[OPEN: exact display format]**
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
- **Assigned**: the admin picks a machine and operator; the order becomes visible to that machine's PLC.
- **In progress**: started at the machine (written by the PLC, or manually by the operator).
- **Completed**: the machine finishes; real quantity recorded; differences calculated.
- **Verified**: warehouse supervisor approval.

Orders can be **partially filled** and **split across machines**.

**Cancellation:** any user except operators can cancel an order, **only before it starts** (*In progress*). After that, an unfinished order is closed short. This may be revisited.

## 8. Inventory

- Inventory moves into the system's database. Products and stock are **imported from the company's existing external database** (structure still being confirmed); CSV/Excel upload remains as a fallback. Whether the external database stays the source of truth (ongoing sync) or is imported once is still **[OPEN]**.
- Tracked items: **products** (by code and presentation, in liters) and **packaging materials** (containers, boxes, bags, labels).
- Product catalog fields: code, name, provider, presentation, **razón social**. Product codes appear to follow a structure (e.g. `GRN100C1XL20F004`, `QVR200C1XL09M01`) **[OPEN: confirm the structure]**.
- **Reservation rule:** when an order is created, every source product (and packaging) is reserved. *Available = on hand − reserved*. The system blocks creating an order if available stock of any source product is insufficient.
- On completion, the real quantities move stock: source products and packaging are consumed, the resulting product is added.
- The system warns when packaging runs low.

## 9. Machines and PLCs

- Around **6 machines**. Any machine can handle any product.
- Each machine has a PLC. **The PLC programming is done separately and is out of our scope.**
- How it works:
  1. The admin assigns an order to a machine; it is saved in the database.
  2. Every X seconds the PLC queries the database for that machine's pending orders.
  3. When it finds one, the PLC signals the operator **on the machine's own screen**.
  4. The PLC **writes every action to the database** (start, progress, pause, completion, quantity dispensed). That is how the system knows an order was completed.
- We send nothing to the PLC. Our part is the database interface: what the PLC reads, what it writes, and access credentials, documented for the PLC programmer.
- **[OPEN: PLC brand/model]** — only matters to confirm the PLC can connect to the database directly or needs a small HTTP gateway.
- If the server or network is down, nothing special is done.

## 10. Users and roles

| Role | Who | Access |
|---|---|---|
| Master admin | Company director | Everything |
| Admin | Office workers | Create and manage work orders, assign machines and operators, cancel orders |
| Supervisor | Warehouse supervisor | Assign, verify, cancel orders, inventory receipts/adjustments **[OPEN: confirm it is a separate role]** |
| Operator | Machine operators | See their assigned orders, fill checklist and materials used |

## 11. Architecture and infrastructure

- Web application for office users and operators.
- Operator interface **[OPEN: tablet or PC at each machine, phone]**. The PLC has its own screen for order alerts.
- Own **API** for the web app.
- Database for orders, inventory, users, machines and PLC events. PLCs access it directly through a restricted interface.
- Hosted on **our own small server** in the office, maintained by an IT person.
- Office and plant are next to each other and on the **same network**. **No VPN**: the system is only reachable from the local network.
- Nightly database backups are kept (already built), though not a formal requirement.
- Programming language: no preference.
- **User interface language: Spanish.** Time zone: America/Mazatlan (UTC−7).

## 12. Decisions made

- Paper work orders are replaced by digital ones; labels are still printed.
- Clients keep ordering by phone; admins create the work orders.
- Inventory is imported from the company's existing external database into the system's database.
- Inventory is reserved at order creation; orders exceeding available stock are blocked.
- An order has one or more source products (ANTES) and one result product (DESPUÉS); quantities in liters.
- Every product belongs to a razón social; the order's razón social sets the operation number suffix, with a separate sequence per razón social.
- Retrabajo has two kinds: of a previous order (linked) and of own stock (no client).
- Expiry defaults to 3 years for normal orders; rework keeps the original expiry.
- PLCs read pending orders from and write their actions to the database; PLC programming is out of scope.
- No VPN; local network only. No handling of server outages. Nightly backups kept.
- Anyone except operators can cancel an order, only before it starts.
- Comments are free text. Packaging materials are tracked as inventory.
- Approvals and verification are lifecycle steps.
- Self-hosted server, Spanish UI, roles: master admin, admin, supervisor, operator.

## 13. Open questions

Numbering is stable; resolved items are kept for reference.

1. ~~*Trabajo* vs *Retrabajo*~~ — **Resolved** (§6).
2. ~~Operation number generation~~ — **Resolved**: sequence per razón social (§6).
3. Meaning of "Reen #" codes in comments.
4. Lot format and expiry display format (expiry rules resolved, §6).
5. Product code structure.
6. PLC brand/model — needed only to confirm how the PLC connects to the database.
7. ~~Mechanism for sending orders to the PLC~~ — **Resolved**: the PLC polls the database (§9).
8. ~~Behavior when the server is down~~ — **Resolved**: nothing is done.
9. Operator device.
10. Supervisor as a separate role.
11. ~~Cancellation rules~~ — **Resolved** (§7).
12. Label and barcode printing integration.
13. ~~Purpose of the VPN~~ — **Resolved**: no VPN.
14. Other sites: do they use this system too?
15. Order volume per day and number of users.
16. Names and codes of the other 2 razones sociales (placeholders used for now).
17. Current operation number of each razón social (to start the sequences).
18. External database: structure, access, and whether it stays the source of truth.

## 14. Glossary

| Spanish | English / meaning |
|---|---|
| Orden de trabajo | Work order |
| Orden de retrabajo | Rework order |
| Razón social | Legal entity the company operates under |
| Antes / Después | Source product(s) / resulting product |
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

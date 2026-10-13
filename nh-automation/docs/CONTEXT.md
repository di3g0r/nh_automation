# Project Context: Work Order and Production Tracking System

> Status: v3 — 2026-10-13 (v2: 2026-10-09, v1: 2026-10-06)
> This document describes the business, the problem, and the decisions made so far. It is the base for the specifications in `docs/specs/`. Items marked **[OPEN]** are not decided yet.
> v3 changes: new **Production manager** role (replaces the supervisor); ANTES/DESPUÉS renamed **Producto base / Producto terminado**; separate numbering for Trabajo (`T-`) and Retrabajo (`R-`); orders can be **paused**; expiry entered by the Production manager (3-year default removed); no office approval step; orders editable until production starts; machines assigned without a specific operator.

---

## 1. The business

The company sells fertilizers and other liquid agricultural products. Production work happens in a plant with filling machines; an office right next to the plant handles orders. The main site is **ECOINDUSTRIAL PACÍFICO**, and there are other sites.

The company operates under several **razones sociales** (legal entities); there are 4 today, for example NOBELTECH (`NB`) and AGRONB (`ANB`). Every product belongs to one razón social.

Clients call the office to order product. The office then creates an internal **work order** (*orden de trabajo*) telling the plant what to do: take one or more base products (for example a 1,000 L tote of a base product), pour or mix them into new containers, label them, and produce the finished product the client ordered.

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
- Let the Production manager see new orders, complete them (expiry, comments) and assign them to machines.
- Let machines (PLCs) pick up their pending orders and record production progress in the database.
- Let the Production manager review completed orders and close them.
- Keep inventory (products and packaging materials) in the system's database, imported from the company's existing database.
- Prevent creating orders for stock that is already committed.
- Later: a dashboard of daily production by machine, operator, product, etc.

## 5. Scope

**First version (focus)**
- User management (CRUD) with roles.
- Work order management (CRUD) with the full lifecycle.
- Catalogs: products, packaging materials, razones sociales, clients, sites, machines.
- Inventory with reservation.
- Assignment of orders to one or more machines by the Production manager.
- Operator view of the machine's orders (pause/resume, checklist, materials used).
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
- **Type**, chosen with a **"Retrabajo" checkbox** when creating the order. It **cannot be changed** afterwards (a Retrabajo can never become a Trabajo, or vice versa).
  - *Trabajo*: normal work order for a client.
  - *Retrabajo* of a **previous order**: modifies an order that was already made; linked to it.
  - *Retrabajo* of **own stock**: we modify our own product for any reason (damaged container, label change, etc.). Not linked to a previous order and has no client.
- **Client:** required, except for *retrabajo* of own stock.
- **Razón social:** defaults to the razón social of the base products; when the order mixes products from different razones sociales, the user chooses which one to use.
- Site (*Lugar*), default ECOINDUSTRIAL PACÍFICO.
- Date.
- **Operation number** (*Número de Operación*): letter + number + razón social code, e.g. `T-447 NB`, `R-12 ANB`.
  - **Trabajo and Retrabajo have independent sequences**, starting at 1, each **shared across all razones sociales** (the next Trabajo after `T-447 NB` could be `T-448 ANB`).
  - The letter (`T` / `R`) avoids duplicates between the two sequences; the type is also displayed clearly on the order.

**Quantitative information**
- **Producto base** (formerly ANTES): **one or more** products (several when products are mixed), each with code, name, provider, presentation and quantity.
- **Producto terminado** (formerly DESPUÉS): one product with code, name, provider, presentation and quantity.
- Quantities are in **liters**.
- **Differences** (*Faltante / Excedente*): calculated automatically from the quantity ordered versus the quantity actually produced. Because of package sizes, a difference **within an acceptable range** is normal **[OPEN: range]**; the Production manager decides by approving the order.

**Comments**: free text (e.g. "Cambio de envase", "Cambio de etiqueta", "Vaciar porrón", "Reen #301"). The admin and the Production manager can **add comments at any time**, before or after the order is finished. Each comment records who wrote it and when. **[OPEN: what "Reen #" codes mean]**

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

**Quality checklist** — normally filled by the Production manager, but any user can fill it; the system records who and when:
- Revisión de lote y etiqueta
- Revisión de niveles de producto
- Revisión de cantidades
- Embalaje

**Traceability**
- Previous lot (*Lote anterior*) and new lot (*Lote posterior*). Normally filled by the Production manager, but any user can; the system records who. **[OPEN: lot format]**
- **Expiry date** (*Fecha de caducidad*):
  - Left **blank** when the order is created. The **Production manager** enters it.
  - **An order cannot start production without an expiry date.**
  - *Retrabajo* of a previous order: copied from that order and **cannot be changed**.
  - *Retrabajo* of own stock: the Production manager enters the original expiry once; then it **cannot be changed**.
  - There is no automatic default (the former 3-year rule no longer applies).
  - On the paper form it appears as e.g. `0326/0329` **[OPEN: exact display format]**.
- Barcode option: 1 barcode per container, or 2 barcodes per box.

**Signatures → system actions** (recorded as user + timestamp): creation (admin), assignment (Production manager), production actions (operator/PLC), closing (Production manager).

## 7. Order lifecycle

```
Creada → Asignada → En proceso ⇄ Pausada → Completada → Cerrada
   └────────┴──→ Cancelada (before production starts)
```

- **Creada**: an admin enters the order; inventory is reserved. The Production manager sees all new orders.
- **Asignada**: the Production manager has entered the expiry date and assigned the order to **one or more machines** (typically 2 when split). The machine quantities must **add up exactly** to the order quantity (e.g. 100 L = 70 L on machine 1 + 30 L on machine 4). The order is now visible to those machines' PLCs.
- **En proceso**: production started on at least one machine (written by the PLC, or manually).
- **Pausada**: production stopped without being finished or cancelled — for example, the shift ended. Any user can pause (normally the operator or the PLC). Each machine pauses independently; the order shows *Pausada* when none of its machines is running. A paused order resumes on the **same machine** **[OPEN: whether the remainder can be moved to another machine]**.
- **Completada**: every machine has finished (normally the PLC marks it). The real quantity and the difference are shown to the Production manager.
- **Cerrada**: the Production manager reviewed and approved the completed order (including any difference within or outside the acceptable range).

**There is no office approval step.**

**Editing:** an order can be edited as many times as needed **before production starts**, by the admin or the Production manager. If the products or quantities change after machines were assigned, the assignment is removed and the Production manager assigns it again. Once production has started, the order cannot be edited (comments can still be added).

**Cancellation:** any user except operators can cancel an order, **only before production starts**.

**The operator** is whoever works on the assigned machine; orders are assigned to machines, not to specific operators. The system records which user (or PLC) performed each action.

## 8. Inventory

- Inventory moves into the system's database. Products and stock are **imported from the company's existing external database** (structure still being confirmed); CSV/Excel upload remains as a fallback. Whether the external database stays the source of truth (ongoing sync) or is imported once is still **[OPEN]**.
- Tracked items: **products** (by code and presentation, in liters) and **packaging materials** (containers, boxes, bags, labels).
- Product catalog fields: code, name, provider, presentation, **razón social**. Product codes appear to follow a structure (e.g. `GRN100C1XL20F004`, `QVR200C1XL09M01`) **[OPEN: confirm the structure]**.
- **Reservation rule:** when an order is created, every base product (and packaging) is reserved. *Available = on hand − reserved*. The system blocks creating an order if available stock of any base product is insufficient.
- On completion, the real quantities move stock: base products and packaging are consumed, the finished product is added.
- The system warns when packaging runs low.

## 9. Machines and PLCs

- Around **6 machines**. Any machine can handle any product.
- Each machine has a PLC. **The PLC programming is done separately and is out of our scope.**
- How it works:
  1. The Production manager assigns an order to one or more machines; it is saved in the database.
  2. Every X seconds the PLC queries the database for that machine's pending orders.
  3. When it finds one, the PLC signals the operator **on the machine's own screen**.
  4. The PLC **writes every action to the database** (start, progress, pause, completion, quantity dispensed). That is how the system knows an order was completed; it then appears to the Production manager for closing.
- We send nothing to the PLC. Our part is the database interface: what the PLC reads, what it writes, and access credentials, documented for the PLC programmer.
- **[OPEN: PLC brand/model]** — only matters to confirm the PLC can connect to the database directly or needs a small HTTP gateway.
- If the server or network is down, nothing special is done.

## 10. Users and roles

| Role | Who | Access |
|---|---|---|
| Master admin | Company director | Everything |
| Admin | Office workers | Create, edit (before production) and cancel orders; add comments; catalogs; inventory |
| Production manager | Plant production manager, the link between the office and the operators | See all orders; create and edit orders (before production); enter expiry; add comments; assign machines; pause/resume; cancel; close completed orders; view inventory |
| Operator | Machine operators | See their machine's orders; start/pause/resume/complete manually when needed; fill checklist, lot and materials used |

There is **no supervisor role** (replaced by the Production manager).

## 11. Architecture and infrastructure

- Web application for office users, the Production manager and operators.
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
- An order has one or more **base products** (Producto base) and one **finished product** (Producto terminado); quantities in liters.
- Every product belongs to a razón social; the order's razón social is the operation number suffix.
- Trabajo and Retrabajo have independent number sequences (`T-` / `R-`), shared across razones sociales, starting at 1. The type is chosen at creation and never changes.
- Retrabajo has two kinds: of a previous order (linked) and of own stock (no client).
- The Production manager enters the expiry date; no order starts without it; rework keeps its original expiry, which cannot be changed. No automatic default.
- Lifecycle: Creada → Asignada → En proceso ⇄ Pausada → Completada → Cerrada; no office approval.
- The Production manager assigns orders to one or more machines whose quantities add up exactly to the order quantity; operators are not assigned individually.
- Orders can be paused (per machine) by any user, normally the operator or the PLC, and resume on the same machine.
- Orders are editable before production starts; changing products or quantities removes the machine assignment.
- Anyone except operators can cancel an order, only before production starts.
- Comments can be added at any time by admins and the Production manager.
- Checklist and lots are normally filled by the Production manager but anyone can; the system records who.
- The Production manager closes completed orders, accepting any difference.
- PLCs read pending orders from and write their actions to the database; PLC programming is out of scope.
- No VPN; local network only. No handling of server outages. Nightly backups kept.
- Self-hosted server, Spanish UI, roles: master admin, admin, Production manager, operator.

## 13. Open questions

Numbering is stable; resolved items are kept for reference.

1. ~~*Trabajo* vs *Retrabajo*~~ — **Resolved** (§6).
2. ~~Operation number generation~~ — **Resolved** (§6, revised v3).
3. Meaning of "Reen #" codes in comments.
4. Lot format and expiry display format.
5. Product code structure.
6. PLC brand/model — needed only to confirm how the PLC connects to the database.
7. ~~Mechanism for sending orders to the PLC~~ — **Resolved**: the PLC polls the database (§9).
8. ~~Behavior when the server is down~~ — **Resolved**: nothing is done.
9. Operator device.
10. ~~Supervisor role~~ — **Resolved**: replaced by the Production manager.
11. ~~Cancellation rules~~ — **Resolved** (§7).
12. Label and barcode printing integration.
13. ~~Purpose of the VPN~~ — **Resolved**: no VPN.
14. Other sites: do they use this system too?
15. Order volume per day and number of users.
16. Names and codes of the other 2 razones sociales (placeholders used for now).
17. ~~Current operation numbers~~ — **Resolved**: sequences start at 1.
18. External database: structure, access, and whether it stays the source of truth.
19. Acceptable range of difference (faltante/excedente) — liters, percentage, or by package size.
20. Whether the remaining quantity of a paused order can be moved to another machine.

## 14. Glossary

| Spanish | English / meaning |
|---|---|
| Orden de trabajo | Work order |
| Orden de retrabajo | Rework order |
| Razón social | Legal entity the company operates under |
| Producto base | Base product(s) used by the order (formerly ANTES) |
| Producto terminado | Finished product (formerly DESPUÉS) |
| Jefe de producción | Production manager |
| Presentación | Presentation (container size, e.g. 1x20 = one 20 L container) |
| Envase | Container |
| Porrón | Large drum / tote |
| Caja | Box |
| Etiqueta | Label |
| Lote | Lot / batch |
| Fecha de caducidad | Expiry date |
| Faltante / Excedente | Shortage / surplus |
| Pausada | Paused (production stopped, not cancelled or finished) |
| Cerrada | Closed (approved by the Production manager) |

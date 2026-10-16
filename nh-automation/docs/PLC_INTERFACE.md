# Interfaz de base de datos para los PLC

> Documento para el programador de los PLC de ECOINDUSTRIAL PACÍFICO.
> Versión 1 — 15/10/2026. Sistema de Órdenes de Trabajo, fase 4.

## 1. Resumen

El sistema **no envía nada al PLC**. Cada PLC:

1. **Lee** cada pocos segundos las órdenes asignadas a su máquina, desde una **vista** de PostgreSQL.
2. Las muestra al operador en la pantalla de la máquina (número de operación, productos, litros, material de empaque, comentarios, caducidad).
3. **Escribe** cada acción del operador (inicio, avance, pausa, reanudación, terminado, error) **insertando una fila** en la tabla `plc_events`.

El sistema procesa cada fila insertada en menos de 5 segundos y actualiza la orden (estado, litros, inventario e historial), exactamente igual que si el jefe de producción hubiera pulsado los botones en la plataforma.

El PLC **solo** puede leer sus vistas e insertar en `plc_events`. No puede leer, modificar ni borrar ninguna otra tabla, ni ver las órdenes de otras máquinas.

## 2. Conexión

| Dato | Valor |
|---|---|
| Motor | PostgreSQL 16 |
| Servidor | Dirección IP del servidor de la oficina (la proporciona el encargado de TI) |
| Puerto | `5432` (salvo que TI indique otro) |
| Base de datos | `nh_automation` (se muestra al generar las credenciales) |
| Usuario | Uno por máquina: `plc_m01`, `plc_m02`, … |
| Contraseña | Se entrega por separado, una por máquina |
| Autenticación | `scram-sha-256` (usuario y contraseña) |
| SSL | No requerido (red local) |

- Las credenciales las genera el director en **Catálogos → Máquinas → Credenciales PLC**. La contraseña se muestra una sola vez; si se pierde, se genera una nueva y la anterior deja de funcionar.
- El servidor solo acepta conexiones de los usuarios PLC desde las direcciones IP autorizadas de las máquinas. Informe a TI la IP fija de cada PLC.
- Cada usuario PLC admite como máximo **3 conexiones simultáneas**. Se recomienda usar **una sola conexión** abierta y reconectar si se pierde.
- Cada consulta tiene un tiempo máximo de **5 segundos**.
- La zona horaria de la sesión es `America/Mazatlan` (UTC−7, sin horario de verano).

## 3. Lo que el PLC lee

Las tres vistas muestran **solo las asignaciones de la máquina del usuario conectado** (no hace falta filtrar por máquina). Solo aparecen órdenes que ya tienen fecha de caducidad y máquinas asignadas, y solo asignaciones `pending`, `running` o `paused`. Al terminar o cancelarse, la asignación desaparece de las vistas.

### 3.1 `plc_pending_assignments` — fila de la máquina

Una fila por asignación, ordenadas por `queue_position`.

| Columna | Tipo | Significado |
|---|---|---|
| `assignment_id` | integer | Identificador de la asignación. **Se usa en todos los eventos.** |
| `operation_number` | text | Número de operación, p. ej. `T-447 NB`, `R-12 ANB` |
| `order_type` | text | `trabajo` o `retrabajo` |
| `queue_position` | integer | `1` = la orden en curso (en proceso o en pausa) o, si no hay, la siguiente por iniciar. Luego 2, 3, … |
| `status` | text | `pending` (por iniciar), `running` (en proceso), `paused` (en pausa) |
| `finished_code` | text | Código del producto terminado |
| `finished_name` | text | Nombre del producto terminado |
| `finished_presentation` | text | Presentación, p. ej. `1X20` |
| `planned_liters` | numeric(12,2) | Litros a producir **en esta máquina** |
| `actual_liters` | numeric(12,2) | Litros registrados hasta ahora (null si aún no hay) |
| `expiry_date` | date | Fecha de caducidad (día 1 del mes; mostrar como `MM/AAAA`) |
| `labels_planned` | integer | Total de etiquetas planeadas de la orden (puede ser null) |
| `barcode_mode` | text | `per_container` (1 código por envase) o `per_box` (2 códigos por caja) |
| `comments` | text | Comentarios de la orden, el más reciente primero, separados por ` \| ` (puede ser null) |

### 3.2 `plc_assignment_base_products` — producto base a usar

| Columna | Tipo | Significado |
|---|---|---|
| `assignment_id` | integer | Asignación |
| `position` | integer | Orden del producto en la orden (1, 2, …) |
| `base_code` | text | Código del producto base |
| `base_name` | text | Nombre del producto base |
| `liters` | numeric(12,2) | Litros de este producto base que corresponden **a esta máquina** |

### 3.3 `plc_assignment_packaging` — material de empaque y etiquetas

| Columna | Tipo | Significado |
|---|---|---|
| `assignment_id` | integer | Asignación |
| `packaging_code` | text | Código del material (envase, caja, bolsa…) |
| `packaging_description` | text | Descripción |
| `planned_qty` | integer | Cantidad planeada **para toda la orden** (si la orden se dividió entre máquinas, es el total) |
| `labels_planned` | integer | Total de etiquetas de la orden |
| `barcode_mode` | text | Igual que en 3.1 |

Una orden puede no tener material de empaque; en ese caso esta vista no tiene filas para ella (las etiquetas y el modo de código de barras también están en 3.1).

### Ejemplos

```sql
-- Fila de la máquina
SELECT assignment_id, queue_position, status, operation_number, order_type,
       finished_code, finished_name, finished_presentation,
       planned_liters, actual_liters, expiry_date, comments
FROM plc_pending_assignments
ORDER BY queue_position;

-- Detalle de la orden actual (assignment_id = 42)
SELECT position, base_code, base_name, liters
FROM plc_assignment_base_products WHERE assignment_id = 42 ORDER BY position;

SELECT packaging_code, packaging_description, planned_qty, labels_planned, barcode_mode
FROM plc_assignment_packaging WHERE assignment_id = 42;
```

## 4. Lo que el PLC escribe: `plc_events`

El PLC solo puede **insertar** (no leer, modificar ni borrar) y solo estas columnas:

| Columna | Tipo | Obligatoria | Significado |
|---|---|---|---|
| `assignment_id` | integer | Sí (salvo `error` de máquina) | La asignación, tomada de `plc_pending_assignments` |
| `event` | text | Sí | `start`, `progress`, `pause`, `resume`, `complete`, `error` |
| `liters` | numeric(12,2) | En `progress` y `complete` | Litros **acumulados** de la asignación (ver 4.2), ≥ 0 |
| `seq` | bigint | No (recomendada) | Número consecutivo por máquina (ver 4.3) |
| `error_code` | varchar(64) | No | Código de error del PLC (en `error`) |
| `message` | text | No | Texto del error (en `error`) |
| `plc_timestamp` | timestamptz | No | Hora del PLC, informativa. Sin zona horaria se toma como hora local de Mazatlán |

La base de datos completa lo demás: la máquina (según el usuario conectado; el PLC no puede elegirla), la hora de recepción y el resultado del procesamiento. Cada inserción también actualiza el **último contacto del PLC** que se ve en el tablero de máquinas.

**No use `INSERT … RETURNING`**: el usuario PLC no tiene permiso de lectura sobre la tabla y la instrucción fallaría.

### 4.1 Eventos

| Evento | Cuándo | Efecto en el sistema |
|---|---|---|
| `start` | El operador inicia la orden | La asignación pasa a *en proceso*; la orden, a *En proceso*. Solo se acepta para la asignación con `queue_position = 1` en estado `pending`, y si la máquina no tiene otra orden en proceso o en pausa |
| `progress` | Cada 5–10 s mientras se produce | Actualiza los litros reales si el valor es **mayor** que el registrado (nunca disminuye) |
| `pause` | El operador pausa (p. ej. fin de turno) | La asignación pasa a *en pausa*; la orden muestra *Pausada* si ninguna de sus máquinas está trabajando. No se libera inventario |
| `resume` | El operador reanuda | Vuelve a *en proceso* (en la misma máquina) |
| `complete` | El operador termina | Litros finales = `liters`. Mueve inventario (consume producto base y agrega producto terminado). Cuando terminan todas las máquinas de la orden, la orden queda *Completada* y pasa al jefe de producción para cerrarla. Se acepta desde *en proceso* o *en pausa* |
| `error` | Falla de la máquina | Se registra en el historial de la orden y en el tablero de máquinas. **No cambia el estado.** Con `assignment_id` nulo se registra como error de la máquina (solo tablero) |

El checklist, los lotes y el material realmente usado los captura después el jefe de producción en la plataforma; el PLC no necesita enviarlos.

### 4.2 Litros acumulados

`liters` es siempre el **total** producido por la máquina para esa asignación desde que inició, **no** la diferencia desde el último envío. Así, si un evento se pierde o llega repetido, el siguiente corrige el valor. Un `progress` con un valor menor al ya registrado se acepta pero no cambia nada.

### 4.3 `seq` y duplicados

`seq` es un número entero que el PLC **incrementa en cada evento** y que **no se reinicia** (debe guardarse en memoria permanente, también tras un corte de energía). Si un evento llega con un `seq` que la máquina ya envió antes, se marca como `duplicate` y no se aplica. Esto permite **reintentar con seguridad** un `INSERT` cuya confirmación no llegó (por ejemplo, por un corte de red): repita exactamente el mismo evento con el mismo `seq`.

Si el PLC **no puede** conservar el contador tras reiniciarse, **no envíe `seq`** (déjelo nulo): un contador que vuelve a empezar haría que los eventos nuevos se descarten como duplicados. Sin `seq` no se detectan duplicados, pero como los litros son acumulados, un `progress` repetido no causa daño; evite repetir `complete`.

### 4.4 Ejemplos

```sql
-- Inicio
INSERT INTO plc_events (assignment_id, event, seq) VALUES (42, 'start', 1001);

-- Avance: 125.5 L producidos en total hasta ahora
INSERT INTO plc_events (assignment_id, event, liters, seq) VALUES (42, 'progress', 125.5, 1002);

-- Pausa y reanudación
INSERT INTO plc_events (assignment_id, event, seq) VALUES (42, 'pause', 1003);
INSERT INTO plc_events (assignment_id, event, seq) VALUES (42, 'resume', 1004);

-- Terminado: 495 L en total
INSERT INTO plc_events (assignment_id, event, liters, seq) VALUES (42, 'complete', 495, 1005);

-- Error durante la orden
INSERT INTO plc_events (assignment_id, event, error_code, message, seq)
VALUES (42, 'error', 'E17', 'Sensor de nivel sin señal', 1006);

-- Error de la máquina sin orden
INSERT INTO plc_events (event, error_code, message, seq)
VALUES ('error', 'E01', 'Paro de emergencia', 1007);
```

### 4.5 Errores al insertar

La base de datos rechaza el `INSERT` (error de PostgreSQL) si:
- `event` no es uno de los seis valores permitidos;
- `liters` es negativo;
- el usuario no está ligado a una máquina activa (máquina dada de baja);
- se intenta escribir una columna no permitida (p. ej. `machine_id`).

En esos casos corrija el programa; reintentar la misma instrucción volverá a fallar.

### 4.6 Eventos rechazados por el sistema

Un `INSERT` válido siempre se guarda, pero el sistema puede **no aplicarlo** si no corresponde al estado de la orden. Queda con `result = 'rejected'` y un motivo en `reject_reason` (formato `CÓDIGO: detalle`):

| Código | Causa típica |
|---|---|
| `NOT_ON_MACHINE` | `assignment_id` no existe o es de otra máquina |
| `NOT_FIRST_IN_QUEUE` | `start` de una asignación que no es la primera de la fila |
| `INVALID_TRANSITION` | Acción no válida en el estado actual: `pause` sin estar en proceso, `start` con otra orden en curso, cualquier evento de una asignación ya terminada o cancelada, máquina en mantenimiento, etc. |
| `BAD_PAYLOAD` | Falta `assignment_id`, o falta `liters` en `progress`/`complete` |
| `INTERNAL_ERROR` | Falla inesperada del sistema (avise a TI) |

Un evento rechazado no detiene los siguientes. El PLC no puede consultar estos resultados (no tiene permiso de lectura sobre `plc_events`); la forma de comprobar que una acción se aplicó es volver a leer `plc_pending_assignments` (estado y `actual_liters`). TI o el desarrollador pueden revisar los eventos rechazados en la base de datos.

## 5. Ciclo recomendado

```
cada N segundos (sugerido: 5):
    filas = SELECT … FROM plc_pending_assignments ORDER BY queue_position
    si no hay filas: mostrar "Sin órdenes"
    actual = fila con queue_position = 1
    si actual.status = 'pending': avisar al operador que hay una orden por iniciar
    mostrar actual + su producto base, material de empaque, comentarios y caducidad

cuando el operador pulsa INICIAR:   insertar 'start'
mientras produce, cada 5–10 s:      insertar 'progress' con los litros acumulados
cuando pulsa PAUSA / REANUDAR:      insertar 'pause' / 'resume'
cuando pulsa TERMINAR:              insertar 'complete' con los litros finales
ante una falla:                     insertar 'error' con código y mensaje
después de cada acción:             releer la vista para confirmar el nuevo estado
```

Notas:
- Una máquina trabaja **una orden a la vez**. La siguiente solo puede iniciarse cuando la actual está terminada.
- Si una orden se divide entre varias máquinas, cada una ve y produce **solo su parte** (`planned_liters`).
- El jefe de producción puede iniciar, pausar, reanudar o terminar desde la plataforma si el PLC falla; el PLC lo verá en el siguiente ciclo de lectura (cambio de `status` o desaparición de la fila).
- La prioridad (`queue_position`) la puede cambiar el jefe de producción en cualquier momento antes de iniciar.
- Si el servidor o la red no están disponibles, no hay un modo sin conexión: reintente la conexión y reenvíe los eventos pendientes con su mismo `seq`.

## 6. Preguntas para el programador del PLC

1. Marca y modelo del PLC y de la pantalla. **¿Puede conectarse directamente a PostgreSQL?** (Si solo puede hacer peticiones HTTP, se construirá una pequeña pasarela HTTP equivalente.)
2. Dirección IP fija de cada PLC (para autorizarla en el servidor).
3. Intervalo de lectura que usará.
4. ¿Puede conservar un contador `seq` en memoria permanente tras reiniciarse?
5. ¿Cómo mide los litros (caudalímetro, báscula, conteo de envases)? ¿Con qué precisión?
6. ¿Puede mostrar textos con acentos y ñ (UTF-8)? ¿Cuántos caracteres por línea?
7. ¿El reloj del PLC está sincronizado? (`plc_timestamp` es solo informativo; el sistema usa su propia hora de recepción.)

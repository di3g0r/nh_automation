import {
  ActionIcon,
  Anchor,
  Badge,
  Button,
  Checkbox,
  Group,
  Pagination,
  Select,
  Stack,
  Table,
  Tabs,
  Text,
  TextInput,
  Title,
  Tooltip,
} from "@mantine/core";
import { useDebouncedValue } from "@mantine/hooks";
import { IconAdjustments, IconHistory, IconPlus } from "@tabler/icons-react";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { sitesApi } from "../api/catalogs";
import { inventoryApi } from "../api/inventory";
import type { InventoryRow, ItemType, MovementType } from "../api/types";
import { AdjustmentModal, ReceiptModal } from "../components/inventory/StockMoveModals";
import { useAuth } from "../context/AuthContext";
import { strings } from "../i18n/strings";
import { CATEGORY_OPTIONS } from "./catalogs/CatalogPages";
import { formatDateTime } from "../utils/datetime";
import { formatQuantity, formatSignedQuantity } from "../utils/quantity";

const t = strings.inventory;
const PAGE_SIZE = 50;

const MOVEMENT_COLOR: Record<MovementType, string> = {
  receipt: "green",
  adjustment: "orange",
  consumption: "red",
  production: "blue",
};

interface ItemFilter {
  item_type: ItemType;
  item_id: number;
  label: string;
}

function useSiteFilterOptions() {
  const { data } = useQuery({
    queryKey: ["sites", "all-for-select"],
    queryFn: () => sitesApi.list({ page_size: 500 }),
  });
  return data?.items.map((s) => ({ value: String(s.id), label: s.name })) ?? [];
}

export function InventoryPage() {
  const { hasPermission } = useAuth();
  const canMove = hasPermission("inventory.move");
  const [params, setParams] = useSearchParams();
  const tab = params.get("tab") ?? "productos";
  const [receiptOpen, setReceiptOpen] = useState(false);
  const [adjustOpen, setAdjustOpen] = useState(false);
  const [itemFilter, setItemFilter] = useState<ItemFilter | null>(null);

  const setTab = (v: string | null) => setParams(v ? { tab: v } : {}, { replace: true });

  const showMovements = (row: InventoryRow) => {
    setItemFilter({
      item_type: row.item_type,
      item_id: row.item_id,
      label: `${row.code} — ${row.name}`,
    });
    setTab("movimientos");
  };

  return (
    <Stack>
      <Group justify="space-between">
        <Title order={2}>{t.title}</Title>
        {canMove && (
          <Group>
            <Button leftSection={<IconPlus size={16} />} onClick={() => setReceiptOpen(true)}>
              {t.entrada}
            </Button>
            <Button
              variant="light"
              leftSection={<IconAdjustments size={16} />}
              onClick={() => setAdjustOpen(true)}
            >
              {t.ajuste}
            </Button>
          </Group>
        )}
      </Group>

      <Tabs value={tab} onChange={setTab} keepMounted={false}>
        <Tabs.List>
          <Tabs.Tab value="productos">{t.tabs.productos}</Tabs.Tab>
          <Tabs.Tab value="materiales">{t.tabs.materiales}</Tabs.Tab>
          <Tabs.Tab value="movimientos">{t.tabs.movimientos}</Tabs.Tab>
        </Tabs.List>
        <Tabs.Panel value="productos" pt="md">
          <StockTab itemType="product" onShowMovements={showMovements} />
        </Tabs.Panel>
        <Tabs.Panel value="materiales" pt="md">
          <StockTab
            itemType="packaging"
            onShowMovements={showMovements}
            initialLowStock={params.get("alertas") === "1"}
          />
        </Tabs.Panel>
        <Tabs.Panel value="movimientos" pt="md">
          <MovementsTab itemFilter={itemFilter} onClearItem={() => setItemFilter(null)} />
        </Tabs.Panel>
      </Tabs>

      {receiptOpen && <ReceiptModal opened onClose={() => setReceiptOpen(false)} />}
      {adjustOpen && <AdjustmentModal opened onClose={() => setAdjustOpen(false)} />}
    </Stack>
  );
}

function StockTab({
  itemType,
  onShowMovements,
  initialLowStock = false,
}: {
  itemType: ItemType;
  onShowMovements: (row: InventoryRow) => void;
  initialLowStock?: boolean;
}) {
  const siteOptions = useSiteFilterOptions();
  const [siteId, setSiteId] = useState<string | null>(null);
  const [category, setCategory] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [debounced] = useDebouncedValue(search, 300);
  const [lowStock, setLowStock] = useState(initialLowStock);
  const [negative, setNegative] = useState(false);
  const [includeInactive, setIncludeInactive] = useState(false);
  const [page, setPage] = useState(1);
  const isPackaging = itemType === "packaging";

  const query = {
    item_type: itemType,
    site_id: siteId ? Number(siteId) : null,
    category: isPackaging ? category : null,
    search: debounced || undefined,
    low_stock: isPackaging && lowStock,
    negative,
    include_inactive: includeInactive,
    page,
    page_size: PAGE_SIZE,
  };
  const { data, isLoading } = useQuery({
    queryKey: ["inventory", "stock", query],
    queryFn: () => inventoryApi.list(query),
  });
  const totalPages = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1;
  const resetPage =
    <T,>(fn: (v: T) => void) =>
    (v: T) => {
      fn(v);
      setPage(1);
    };
  const colCount = isPackaging ? 9 : 8;

  return (
    <Stack>
      <Group align="end">
        <TextInput
          placeholder={t.filtros.buscar}
          value={search}
          onChange={(e) => resetPage(setSearch)(e.currentTarget.value)}
          w={300}
        />
        <Select
          placeholder={t.filtros.todosSitios}
          data={siteOptions}
          value={siteId}
          onChange={resetPage(setSiteId)}
          clearable
          w={240}
        />
        {isPackaging && (
          <Select
            placeholder={t.filtros.categoria}
            data={CATEGORY_OPTIONS}
            value={category}
            onChange={resetPage(setCategory)}
            clearable
            w={180}
          />
        )}
        {isPackaging && (
          <Checkbox
            label={t.filtros.stockBajo}
            checked={lowStock}
            onChange={(e) => resetPage(setLowStock)(e.currentTarget.checked)}
          />
        )}
        <Checkbox
          label={t.filtros.negativo}
          checked={negative}
          onChange={(e) => resetPage(setNegative)(e.currentTarget.checked)}
        />
        <Checkbox
          label={t.filtros.inactivos}
          checked={includeInactive}
          onChange={(e) => resetPage(setIncludeInactive)(e.currentTarget.checked)}
        />
      </Group>

      <Table.ScrollContainer minWidth={800}>
        <Table striped highlightOnHover>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>{t.columnas.codigo}</Table.Th>
              <Table.Th>{t.columnas.nombre}</Table.Th>
              {isPackaging && <Table.Th>{t.columnas.categoria}</Table.Th>}
              <Table.Th>{t.columnas.sitio}</Table.Th>
              <Table.Th ta="right">{t.columnas.existencia}</Table.Th>
              <Table.Th ta="right">{t.columnas.reservado}</Table.Th>
              <Table.Th ta="right">{t.columnas.disponible}</Table.Th>
              <Table.Th>{t.columnas.alertas}</Table.Th>
              <Table.Th w={40} />
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {!isLoading && data?.items.length === 0 && (
              <Table.Tr>
                <Table.Td colSpan={colCount}>
                  <Text c="dimmed">{strings.common.sinDatos}</Text>
                </Table.Td>
              </Table.Tr>
            )}
            {data?.items.map((r) => (
              <Table.Tr key={`${r.item_id}-${r.site_id}`} opacity={r.is_active ? 1 : 0.6}>
                <Table.Td>{r.code}</Table.Td>
                <Table.Td>{r.name}</Table.Td>
                {isPackaging && (
                  <Table.Td>
                    {r.category ? strings.catalogs.packaging.categories[r.category] : ""}
                  </Table.Td>
                )}
                <Table.Td>{r.site_name}</Table.Td>
                <Table.Td ta="right" c={r.negative ? "red" : undefined}>
                  {formatQuantity(r.item_type, r.on_hand)}
                </Table.Td>
                <Table.Td ta="right">{formatQuantity(r.item_type, r.reserved)}</Table.Td>
                <Table.Td ta="right" fw={500}>
                  {formatQuantity(r.item_type, r.available)}
                </Table.Td>
                <Table.Td>
                  <Group gap={4}>
                    {r.low_stock && (
                      <Tooltip
                        label={`${strings.alerts.umbral}: ${formatQuantity(
                          "packaging",
                          r.low_stock_threshold ?? 0,
                        )}`}
                      >
                        <Badge color="orange">{t.badges.stockBajo}</Badge>
                      </Tooltip>
                    )}
                    {r.negative && <Badge color="red">{t.badges.negativo}</Badge>}
                    {!r.is_active && <Badge color="gray">{t.badges.inactivo}</Badge>}
                  </Group>
                </Table.Td>
                <Table.Td>
                  <Tooltip label={t.verMovimientos}>
                    <ActionIcon
                      variant="subtle"
                      aria-label={t.verMovimientos}
                      onClick={() => onShowMovements(r)}
                    >
                      <IconHistory size={16} />
                    </ActionIcon>
                  </Tooltip>
                </Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      </Table.ScrollContainer>
      {totalPages > 1 && <Pagination value={page} onChange={setPage} total={totalPages} />}
    </Stack>
  );
}

function MovementsTab({
  itemFilter,
  onClearItem,
}: {
  itemFilter: ItemFilter | null;
  onClearItem: () => void;
}) {
  const m = t.movimientos;
  const siteOptions = useSiteFilterOptions();
  const { data: users } = useQuery({
    queryKey: ["inventory", "movement-users"],
    queryFn: inventoryApi.movementUsers,
  });
  const [itemType, setItemType] = useState<string | null>(null);
  const [type, setType] = useState<string | null>(null);
  const [siteId, setSiteId] = useState<string | null>(null);
  const [userId, setUserId] = useState<string | null>(null);
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [page, setPage] = useState(1);

  const query = {
    item_type: itemFilter?.item_type ?? (itemType as ItemType | null),
    item_id: itemFilter?.item_id ?? null,
    type: type as MovementType | null,
    site_id: siteId ? Number(siteId) : null,
    user_id: userId ? Number(userId) : null,
    date_from: dateFrom || null,
    date_to: dateTo || null,
    page,
    page_size: PAGE_SIZE,
  };
  const { data, isLoading } = useQuery({
    queryKey: ["inventory", "movements", query],
    queryFn: () => inventoryApi.movements(query),
  });
  const totalPages = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1;
  const typeOptions = (Object.keys(t.tiposMovimiento) as MovementType[]).map((v) => ({
    value: v,
    label: t.tiposMovimiento[v],
  }));

  const clear = () => {
    setItemType(null);
    setType(null);
    setSiteId(null);
    setUserId(null);
    setDateFrom("");
    setDateTo("");
    setPage(1);
    onClearItem();
  };
  const withReset =
    <T,>(fn: (v: T) => void) =>
    (v: T) => {
      fn(v);
      setPage(1);
    };

  return (
    <Stack>
      {itemFilter && (
        <Group>
          <Badge size="lg" variant="light">
            {m.filtrandoArticulo}: {itemFilter.label}
          </Badge>
        </Group>
      )}
      <Group align="end">
        {!itemFilter && (
          <Select
            label={t.form.tipoArticulo}
            placeholder={m.todos}
            data={[
              { value: "product", label: t.form.producto },
              { value: "packaging", label: t.form.material },
            ]}
            value={itemType}
            onChange={withReset(setItemType)}
            clearable
            w={190}
          />
        )}
        <Select
          label={m.tipo}
          placeholder={m.todos}
          data={typeOptions}
          value={type}
          onChange={withReset(setType)}
          clearable
          w={160}
        />
        <Select
          label={t.filtros.sitio}
          placeholder={t.filtros.todosSitios}
          data={siteOptions}
          value={siteId}
          onChange={withReset(setSiteId)}
          clearable
          w={220}
        />
        <Select
          label={m.usuario}
          placeholder={m.todos}
          data={users?.map((u) => ({ value: String(u.id), label: u.full_name })) ?? []}
          value={userId}
          onChange={withReset(setUserId)}
          clearable
          searchable
          w={200}
        />
        <TextInput
          type="date"
          label={m.desde}
          value={dateFrom}
          onChange={(e) => withReset(setDateFrom)(e.currentTarget.value)}
        />
        <TextInput
          type="date"
          label={m.hasta}
          value={dateTo}
          onChange={(e) => withReset(setDateTo)(e.currentTarget.value)}
        />
        <Button variant="subtle" onClick={clear}>
          {m.limpiar}
        </Button>
      </Group>

      <Table.ScrollContainer minWidth={900}>
        <Table striped highlightOnHover>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>{m.fecha}</Table.Th>
              <Table.Th>{m.tipo}</Table.Th>
              <Table.Th>{m.articulo}</Table.Th>
              <Table.Th>{t.columnas.sitio}</Table.Th>
              <Table.Th ta="right">{m.cantidad}</Table.Th>
              <Table.Th>{m.usuario}</Table.Th>
              <Table.Th>{m.nota}</Table.Th>
              <Table.Th>{m.referencia}</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {!isLoading && data?.items.length === 0 && (
              <Table.Tr>
                <Table.Td colSpan={8}>
                  <Text c="dimmed">{strings.common.sinDatos}</Text>
                </Table.Td>
              </Table.Tr>
            )}
            {data?.items.map((mv) => (
              <Table.Tr key={mv.id}>
                <Table.Td>{formatDateTime(mv.created_at)}</Table.Td>
                <Table.Td>
                  <Badge color={MOVEMENT_COLOR[mv.type]} variant="light">
                    {t.tiposMovimiento[mv.type]}
                  </Badge>
                </Table.Td>
                <Table.Td>
                  <Text size="sm" fw={500}>
                    {mv.item_code}
                  </Text>
                  <Text size="xs" c="dimmed">
                    {mv.item_name}
                  </Text>
                </Table.Td>
                <Table.Td>{mv.site_name}</Table.Td>
                <Table.Td ta="right" c={Number(mv.quantity) < 0 ? "red" : "green"}>
                  {formatSignedQuantity(mv.item_type, mv.quantity)}
                </Table.Td>
                <Table.Td>{mv.user_name ?? strings.audit.sinUsuario}</Table.Td>
                <Table.Td>{mv.note}</Table.Td>
                <Table.Td>
                  {/* Orders/assignments arrive in phases 2-3; their pages own these routes. */}
                  {mv.order_id && (
                    <Anchor component={Link} to={`/ordenes/${mv.order_id}`} size="sm">
                      {m.orden} #{mv.order_id}
                    </Anchor>
                  )}
                  {mv.assignment_id && (
                    <Text size="xs" c="dimmed">
                      {m.asignacion} #{mv.assignment_id}
                    </Text>
                  )}
                </Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      </Table.ScrollContainer>
      {totalPages > 1 && <Pagination value={page} onChange={setPage} total={totalPages} />}
    </Stack>
  );
}

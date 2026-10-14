import {
  Badge,
  Button,
  Group,
  MultiSelect,
  Pagination,
  Select,
  Stack,
  Table,
  Text,
  TextInput,
  Title,
  Tooltip,
} from "@mantine/core";
import { useDebouncedValue } from "@mantine/hooks";
import { IconAlertTriangle, IconPlus } from "@tabler/icons-react";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { clientsApi, razonesSocialesApi, sitesApi } from "../../api/catalogs";
import { ordersApi } from "../../api/orders";
import type { OrderStatus, OrderType, Product } from "../../api/types";
import { OrderStatusBadge, OrderTypeBadge } from "../../components/orders/OrderBadges";
import { ProductSelect } from "../../components/orders/ProductSelect";
import { useAuth } from "../../context/AuthContext";
import { strings } from "../../i18n/strings";
import { formatLiters } from "../../utils/datetime";
import { formatPlainDate } from "../../utils/orders";

const t = strings.orders;
const PAGE_SIZE = 50;

function useFilterOptions() {
  const clients = useQuery({
    queryKey: ["clients", "all-for-select"],
    queryFn: () => clientsApi.list({ page_size: 500 }),
  });
  const razones = useQuery({
    queryKey: ["razones-sociales", "all-for-select"],
    queryFn: () => razonesSocialesApi.list({ page_size: 500 }),
  });
  const sites = useQuery({
    queryKey: ["sites", "all-for-select"],
    queryFn: () => sitesApi.list({ page_size: 500 }),
  });
  return {
    clients: clients.data?.items.map((c) => ({ value: String(c.id), label: c.name })) ?? [],
    razones:
      razones.data?.items.map((r) => ({ value: String(r.id), label: `${r.code} — ${r.name}` })) ??
      [],
    sites: sites.data?.items.map((s) => ({ value: String(s.id), label: s.name })) ?? [],
  };
}

/** FR-ORD-2: list with filters, newest first. */
export function OrdersListPage() {
  const navigate = useNavigate();
  const { hasPermission } = useAuth();
  const options = useFilterOptions();
  const [statuses, setStatuses] = useState<string[]>([]);
  const [orderType, setOrderType] = useState<string | null>(null);
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [clientId, setClientId] = useState<string | null>(null);
  const [rsId, setRsId] = useState<string | null>(null);
  const [siteId, setSiteId] = useState<string | null>(null);
  const [product, setProduct] = useState<Product | null>(null);
  const [search, setSearch] = useState("");
  const [debounced] = useDebouncedValue(search, 300);
  const [page, setPage] = useState(1);

  const params = {
    status: statuses.join(",") || null,
    order_type: orderType as OrderType | null,
    date_from: dateFrom || null,
    date_to: dateTo || null,
    client_id: clientId ? Number(clientId) : null,
    razon_social_id: rsId ? Number(rsId) : null,
    site_id: siteId ? Number(siteId) : null,
    product_id: product?.id ?? null,
    search: debounced || undefined,
    page,
    page_size: PAGE_SIZE,
  };
  const { data, isLoading } = useQuery({
    queryKey: ["orders", "list", params],
    queryFn: () => ordersApi.list(params),
  });
  const totalPages = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1;
  const withReset =
    <T,>(fn: (v: T) => void) =>
    (v: T) => {
      fn(v);
      setPage(1);
    };
  const clear = () => {
    setStatuses([]);
    setOrderType(null);
    setDateFrom("");
    setDateTo("");
    setClientId(null);
    setRsId(null);
    setSiteId(null);
    setProduct(null);
    setSearch("");
    setPage(1);
  };

  const statusOptions = (Object.keys(t.estados) as OrderStatus[]).map((s) => ({
    value: s,
    label: t.estados[s],
  }));

  return (
    <Stack>
      <Group justify="space-between">
        <Title order={2}>{t.title}</Title>
        {hasPermission("orders.edit") && (
          <Button leftSection={<IconPlus size={16} />} onClick={() => navigate("/ordenes/nueva")}>
            {t.nueva}
          </Button>
        )}
      </Group>

      <Group align="end" gap="sm">
        <TextInput
          label={t.columnas.numero}
          placeholder={t.buscar}
          value={search}
          onChange={(e) => withReset(setSearch)(e.currentTarget.value)}
          w={220}
        />
        <MultiSelect
          label={t.filtros.estado}
          placeholder={statuses.length ? undefined : t.filtros.todos}
          data={statusOptions}
          value={statuses}
          onChange={withReset(setStatuses)}
          clearable
          w={260}
        />
        <Select
          label={t.filtros.tipo}
          placeholder={t.filtros.todos}
          data={[
            { value: "trabajo", label: t.tiposFiltro.trabajo },
            { value: "retrabajo", label: t.tiposFiltro.retrabajo },
          ]}
          value={orderType}
          onChange={withReset(setOrderType)}
          clearable
          w={140}
        />
        <TextInput
          type="date"
          label={t.filtros.desde}
          value={dateFrom}
          onChange={(e) => withReset(setDateFrom)(e.currentTarget.value)}
        />
        <TextInput
          type="date"
          label={t.filtros.hasta}
          value={dateTo}
          onChange={(e) => withReset(setDateTo)(e.currentTarget.value)}
        />
      </Group>
      <Group align="end" gap="sm">
        <Select
          label={t.filtros.cliente}
          placeholder={t.filtros.todos}
          data={options.clients}
          value={clientId}
          onChange={withReset(setClientId)}
          clearable
          searchable
          w={220}
        />
        <Select
          label={t.filtros.razonSocial}
          placeholder={t.filtros.todos}
          data={options.razones}
          value={rsId}
          onChange={withReset(setRsId)}
          clearable
          w={200}
        />
        <ProductSelect
          label={t.filtros.producto}
          value={product}
          onChange={withReset(setProduct)}
          w={320}
        />
        <Select
          label={t.filtros.sitio}
          placeholder={t.filtros.todos}
          data={options.sites}
          value={siteId}
          onChange={withReset(setSiteId)}
          clearable
          w={220}
        />
        <Button variant="subtle" onClick={clear}>
          {t.filtros.limpiar}
        </Button>
      </Group>

      <Table.ScrollContainer minWidth={1000}>
        <Table striped highlightOnHover>
          <Table.Thead>
            <Table.Tr>
              <Table.Th>{t.columnas.numero}</Table.Th>
              <Table.Th>{t.columnas.tipo}</Table.Th>
              <Table.Th>{t.columnas.estado}</Table.Th>
              <Table.Th>{t.columnas.fecha}</Table.Th>
              <Table.Th>{t.columnas.cliente}</Table.Th>
              <Table.Th>{t.columnas.productoBase}</Table.Th>
              <Table.Th>{t.columnas.productoTerminado}</Table.Th>
              <Table.Th ta="right">{t.columnas.litros}</Table.Th>
              <Table.Th>{t.columnas.sitio}</Table.Th>
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {!isLoading && data?.items.length === 0 && (
              <Table.Tr>
                <Table.Td colSpan={9}>
                  <Text c="dimmed">{strings.common.sinDatos}</Text>
                </Table.Td>
              </Table.Tr>
            )}
            {data?.items.map((o) => (
              <Table.Tr
                key={o.id}
                style={{ cursor: "pointer" }}
                onClick={() => navigate(`/ordenes/${o.id}`)}
              >
                <Table.Td>
                  <Group gap={6} wrap="nowrap">
                    <Text fw={600}>{o.operation_number}</Text>
                    {o.has_warnings && (
                      <Tooltip label={t.conAvisos}>
                        <IconAlertTriangle size={16} color="orange" />
                      </Tooltip>
                    )}
                  </Group>
                </Table.Td>
                <Table.Td>
                  <OrderTypeBadge type={o.order_type} size="sm" />
                </Table.Td>
                <Table.Td>
                  <OrderStatusBadge status={o.status} size="sm" />
                </Table.Td>
                <Table.Td>{formatPlainDate(o.order_date)}</Table.Td>
                <Table.Td>
                  {o.client_name ?? (
                    <Badge variant="outline" color="gray" size="sm">
                      {t.reworkKinds.own_stock}
                    </Badge>
                  )}
                </Table.Td>
                <Table.Td>
                  {o.base_products.map((b) => (
                    <Text key={b} size="xs">
                      {b}
                    </Text>
                  ))}
                </Table.Td>
                <Table.Td>
                  <Text size="sm">{o.finished_code}</Text>
                  <Text size="xs" c="dimmed">
                    {o.finished_name}
                  </Text>
                </Table.Td>
                <Table.Td ta="right">{formatLiters(o.finished_liters)}</Table.Td>
                <Table.Td>{o.site_name}</Table.Td>
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      </Table.ScrollContainer>
      {totalPages > 1 && <Pagination value={page} onChange={setPage} total={totalPages} />}
    </Stack>
  );
}

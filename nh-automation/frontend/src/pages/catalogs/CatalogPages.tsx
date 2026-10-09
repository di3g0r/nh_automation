import { Badge, Button, Group, Modal, Select, Stack, Text } from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { IconFileImport } from "@tabler/icons-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";

import { clientsApi, machinesApi, packagingApi, productsApi, sitesApi } from "../../api/catalogs";
import type {
  Client,
  ImportKind,
  Machine,
  MachineWithKey,
  PackagingCategory,
  PackagingItem,
  Product,
  Site,
} from "../../api/types";
import { CatalogPage } from "../../components/catalogs/CatalogPage";
import type { CatalogConfig } from "../../components/catalogs/CatalogPage";
import { ImportModal } from "../../components/catalogs/ImportModal";
import { MachineKeyModal } from "../../components/catalogs/MachineKeyModal";
import { strings } from "../../i18n/strings";
import { formatDateTime, formatLiters } from "../../utils/datetime";
import { notifyError } from "../../utils/notify";

const t = strings.catalogs;

export const CATEGORY_OPTIONS = (Object.keys(t.packaging.categories) as PackagingCategory[]).map(
  (value) => ({ value, label: t.packaging.categories[value] }),
);

function ImportButton({ kind, queryKey }: { kind: ImportKind; queryKey: string }) {
  const [opened, setOpened] = useState(false);
  const queryClient = useQueryClient();
  return (
    <>
      <Button
        variant="default"
        leftSection={<IconFileImport size={16} />}
        onClick={() => setOpened(true)}
      >
        {t.importar}
      </Button>
      <ImportModal
        kind={kind}
        opened={opened}
        onClose={() => setOpened(false)}
        onDone={() => {
          queryClient.invalidateQueries({ queryKey: [queryKey] });
          queryClient.invalidateQueries({ queryKey: ["inventory"] });
        }}
      />
    </>
  );
}

// Productos ---------------------------------------------------------------------

export function ProductsPage() {
  const p = t.products;
  const config: CatalogConfig<Product> = {
    queryKey: "products",
    title: p.title,
    newLabel: p.nuevo,
    searchPlaceholder: p.buscar,
    list: productsApi.list,
    create: productsApi.create,
    update: productsApi.update,
    toolbar: <ImportButton kind="products" queryKey="products" />,
    columns: [
      { label: p.code, render: (r) => r.code },
      { label: p.name, render: (r) => r.name },
      { label: p.provider, render: (r) => r.provider },
      { label: p.presentation, render: (r) => r.presentation },
      {
        label: p.container_liters,
        render: (r) => (r.container_liters ? formatLiters(r.container_liters) : "—"),
      },
    ],
    fields: [
      { name: "code", label: p.code, type: "text", required: true },
      { name: "name", label: p.name, type: "text", required: true },
      { name: "provider", label: p.provider, type: "text", required: true },
      {
        name: "presentation",
        label: p.presentation,
        type: "text",
        required: true,
        description: p.presentationHint,
      },
      { name: "container_liters", label: p.container_liters, type: "decimal" },
    ],
  };
  return <CatalogPage config={config} />;
}

// Materiales de empaque -----------------------------------------------------------

export function PackagingPage() {
  const p = t.packaging;
  const [category, setCategory] = useState<string | null>(null);
  const config: CatalogConfig<PackagingItem> = {
    queryKey: "packaging-items",
    title: p.title,
    newLabel: p.nuevo,
    searchPlaceholder: p.buscar,
    list: packagingApi.list,
    create: packagingApi.create,
    update: packagingApi.update,
    toolbar: <ImportButton kind="packaging-items" queryKey="packaging-items" />,
    filters: (
      <Select
        placeholder={p.category}
        data={CATEGORY_OPTIONS}
        value={category}
        onChange={setCategory}
        clearable
        w={180}
      />
    ),
    extraParams: { category: category ?? undefined },
    columns: [
      { label: p.code, render: (r) => r.code },
      { label: p.description, render: (r) => r.description },
      { label: p.category, render: (r) => p.categories[r.category] },
      {
        label: p.low_stock_threshold,
        render: (r) => r.low_stock_threshold.toLocaleString("en-US"),
      },
    ],
    fields: [
      { name: "code", label: p.code, type: "text", required: true },
      { name: "description", label: p.description, type: "text", required: true },
      {
        name: "category",
        label: p.category,
        type: "select",
        required: true,
        options: CATEGORY_OPTIONS,
      },
      { name: "low_stock_threshold", label: p.low_stock_threshold, type: "int" },
    ],
  };
  return <CatalogPage config={config} />;
}

// Clientes ------------------------------------------------------------------------

export function ClientsPage() {
  const c = t.clients;
  const config: CatalogConfig<Client> = {
    queryKey: "clients",
    title: c.title,
    newLabel: c.nuevo,
    searchPlaceholder: c.buscar,
    list: clientsApi.list,
    create: clientsApi.create,
    update: clientsApi.update,
    columns: [
      { label: c.name, render: (r) => r.name },
      { label: c.code, render: (r) => r.code },
    ],
    fields: [
      { name: "name", label: c.name, type: "text", required: true },
      { name: "code", label: c.code, type: "text", required: true, description: c.codeHint },
    ],
  };
  return <CatalogPage config={config} />;
}

// Sitios --------------------------------------------------------------------------

export function SitesPage() {
  const s = t.sites;
  const queryClient = useQueryClient();
  const makeDefault = useMutation({
    mutationFn: (row: Site) => sitesApi.update(row.id, { is_default: true }),
    onSuccess: () => {
      notifications.show({ message: t.actualizado, color: "green" });
      queryClient.invalidateQueries({ queryKey: ["sites"] });
    },
    onError: notifyError,
  });
  const config: CatalogConfig<Site> = {
    queryKey: "sites",
    title: s.title,
    newLabel: s.nuevo,
    searchPlaceholder: s.buscar,
    list: sitesApi.list,
    create: sitesApi.create,
    update: sitesApi.update,
    columns: [
      { label: s.name, render: (r) => r.name },
      {
        label: s.is_default,
        render: (r) => (r.is_default ? <Badge color="blue">{s.predeterminado}</Badge> : ""),
      },
    ],
    // The default flag is changed with its own action so there is always exactly one.
    fields: [
      { name: "name", label: s.name, type: "text", required: true },
      { name: "is_default", label: s.is_default, type: "checkbox", createOnly: true },
    ],
    rowActions: [
      {
        label: s.marcarPredeterminado,
        hidden: (r) => r.is_default || !r.is_active,
        onClick: (r) => makeDefault.mutate(r),
      },
    ],
  };
  return <CatalogPage config={config} />;
}

// Máquinas ------------------------------------------------------------------------

export function MachinesPage() {
  const m = t.machines;
  const queryClient = useQueryClient();
  const [shownKey, setShownKey] = useState<MachineWithKey | null>(null);
  const [rotating, setRotating] = useState<Machine | null>(null);

  const { data: sites } = useQuery({
    queryKey: ["sites", "all-for-select"],
    queryFn: () => sitesApi.list({ page_size: 500 }),
  });
  // Inactive sites stay listed (old records display them) but can't be picked.
  const siteOptions = useMemo(
    () =>
      sites?.items.map((s) => ({
        value: String(s.id),
        label: s.is_active ? s.name : `${s.name} ${m.inactivoSufijo}`,
        disabled: !s.is_active,
      })) ?? [],
    [sites, m.inactivoSufijo],
  );
  const defaultSite = sites?.items.find((s) => s.is_default);

  const rotate = useMutation({
    mutationFn: (row: Machine) => machinesApi.rotateKey(row.id),
    onSuccess: (res) => {
      setRotating(null);
      setShownKey(res);
      queryClient.invalidateQueries({ queryKey: ["machines"] });
    },
    onError: notifyError,
  });

  const config: CatalogConfig<Machine> = {
    queryKey: "machines",
    title: m.title,
    newLabel: m.nuevo,
    searchPlaceholder: m.buscar,
    list: machinesApi.list,
    create: (payload) =>
      machinesApi.create({ site_id: defaultSite?.id, ...payload } as Partial<Machine>),
    update: machinesApi.update,
    onCreated: (res) => setShownKey(res as MachineWithKey),
    columns: [
      { label: m.code, render: (r) => r.code },
      { label: m.name, render: (r) => r.name },
      { label: m.site, render: (r) => r.site_name },
      {
        label: m.mantenimiento,
        render: (r) => (r.in_maintenance ? <Badge color="orange">{t.si}</Badge> : t.no),
      },
      {
        label: m.llave,
        render: (r) =>
          r.has_api_key ? (
            <Badge color="teal" variant="light">
              {m.conLlave}
            </Badge>
          ) : (
            <Badge color="gray" variant="light">
              {m.sinLlave}
            </Badge>
          ),
      },
      { label: m.ultimaSenal, render: (r) => formatDateTime(r.last_seen_at) || "—" },
    ],
    fields: [
      { name: "code", label: m.code, type: "text", required: true },
      { name: "name", label: m.name, type: "text", required: true },
      {
        name: "site_id",
        label: m.site,
        type: "select",
        required: true,
        asNumber: true,
        options: siteOptions,
      },
      { name: "in_maintenance", label: m.in_maintenance, type: "checkbox" },
    ],
    rowActions: [{ label: m.rotarLlave, color: "orange", onClick: (r) => setRotating(r) }],
  };

  return (
    <>
      <CatalogPage config={config} />
      <MachineKeyModal data={shownKey} onClose={() => setShownKey(null)} />
      <Modal opened={rotating !== null} onClose={() => setRotating(null)} title={m.rotarLlave}>
        <Stack>
          <Text>
            {rotating?.code} — {rotating?.name}
          </Text>
          <Text size="sm">{m.rotarConfirm}</Text>
          <Group justify="end">
            <Button variant="default" onClick={() => setRotating(null)}>
              {strings.common.cancelar}
            </Button>
            <Button
              color="orange"
              loading={rotate.isPending}
              onClick={() => rotating && rotate.mutate(rotating)}
            >
              {m.rotarLlave}
            </Button>
          </Group>
        </Stack>
      </Modal>
    </>
  );
}

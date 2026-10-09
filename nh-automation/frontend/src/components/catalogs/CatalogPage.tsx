import {
  ActionIcon,
  Badge,
  Button,
  Checkbox,
  Group,
  Menu,
  Modal,
  Pagination,
  SegmentedControl,
  Select,
  Stack,
  Table,
  Text,
  TextInput,
  Title,
} from "@mantine/core";
import { useDebouncedValue } from "@mantine/hooks";
import { notifications } from "@mantine/notifications";
import { IconDots, IconPlus } from "@tabler/icons-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import type { ReactNode } from "react";

import type { ListParams } from "../../api/catalogs";
import { ApiError } from "../../api/client";
import type { Page } from "../../api/types";
import { useAuth } from "../../context/AuthContext";
import { strings } from "../../i18n/strings";
import { notifyError } from "../../utils/notify";
import { toPayload } from "./catalogForm";
import type { FieldDef, FieldValue } from "./catalogForm";

const PAGE_SIZE = 50;
const t = strings.catalogs;

export interface ColumnDef<T> {
  label: string;
  render: (row: T) => ReactNode;
}

export interface RowAction<T> {
  label: string;
  color?: string;
  hidden?: (row: T) => boolean;
  onClick: (row: T) => void;
}

export interface CatalogConfig<T extends { id: number; is_active: boolean }> {
  queryKey: string;
  title: string;
  newLabel: string;
  searchPlaceholder: string;
  columns: ColumnDef<T>[];
  fields: FieldDef[];
  list: (params: ListParams) => Promise<Page<T>>;
  create: (payload: Record<string, unknown>) => Promise<unknown>;
  update: (id: number, payload: Record<string, unknown>) => Promise<T>;
  /** Called with the create response (machines show their API key here). */
  onCreated?: (result: unknown) => void;
  rowActions?: RowAction<T>[];
  toolbar?: ReactNode;
  /** Optional extra filter control rendered next to search, plus its params. */
  filters?: ReactNode;
  extraParams?: Partial<ListParams>;
}

export function ActiveBadge({ active }: { active: boolean }) {
  return <Badge color={active ? "green" : "gray"}>{active ? t.activo : t.inactivo}</Badge>;
}

export function CatalogPage<T extends { id: number; is_active: boolean }>({
  config,
}: {
  config: CatalogConfig<T>;
}) {
  const { hasPermission } = useAuth();
  const canManage = hasPermission("catalogs.manage");
  const queryClient = useQueryClient();
  const [search, setSearch] = useState("");
  const [debouncedSearch] = useDebouncedValue(search, 300);
  const [activeFilter, setActiveFilter] = useState<"active" | "inactive" | "all">("active");
  const [page, setPage] = useState(1);
  const [editing, setEditing] = useState<T | "new" | null>(null);

  const params: ListParams = {
    search: debouncedSearch || undefined,
    active: activeFilter === "all" ? undefined : activeFilter === "active",
    page,
    page_size: PAGE_SIZE,
    ...config.extraParams,
  };
  const { data, isLoading } = useQuery({
    queryKey: [config.queryKey, params],
    queryFn: () => config.list(params),
  });

  const invalidate = () => queryClient.invalidateQueries({ queryKey: [config.queryKey] });

  const toggleActive = useMutation({
    mutationFn: (row: T) => config.update(row.id, { is_active: !row.is_active }),
    onSuccess: (row) => {
      notifications.show({ message: row.is_active ? t.activado : t.desactivado, color: "green" });
      invalidate();
    },
    onError: notifyError,
  });

  const totalPages = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1;
  const colCount = config.columns.length + 1 + (canManage ? 1 : 0);

  return (
    <Stack>
      <Group justify="space-between">
        <Title order={2}>{config.title}</Title>
        {canManage && (
          <Group>
            {config.toolbar}
            <Button leftSection={<IconPlus size={16} />} onClick={() => setEditing("new")}>
              {config.newLabel}
            </Button>
          </Group>
        )}
      </Group>

      <Group align="end">
        <TextInput
          placeholder={config.searchPlaceholder}
          value={search}
          onChange={(e) => {
            setSearch(e.currentTarget.value);
            setPage(1);
          }}
          w={340}
        />
        <SegmentedControl
          value={activeFilter}
          onChange={(v) => {
            setActiveFilter(v as typeof activeFilter);
            setPage(1);
          }}
          data={[
            { value: "active", label: t.filtroActivos },
            { value: "inactive", label: t.filtroInactivos },
            { value: "all", label: t.filtroTodos },
          ]}
        />
        {config.filters}
      </Group>

      <Table.ScrollContainer minWidth={640}>
        <Table striped highlightOnHover>
          <Table.Thead>
            <Table.Tr>
              {config.columns.map((c) => (
                <Table.Th key={c.label}>{c.label}</Table.Th>
              ))}
              <Table.Th>{t.estado}</Table.Th>
              {canManage && <Table.Th w={60}>{t.acciones}</Table.Th>}
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {isLoading && (
              <Table.Tr>
                <Table.Td colSpan={colCount}>
                  <Text c="dimmed">{strings.common.cargando}</Text>
                </Table.Td>
              </Table.Tr>
            )}
            {!isLoading && data?.items.length === 0 && (
              <Table.Tr>
                <Table.Td colSpan={colCount}>
                  <Text c="dimmed">{strings.common.sinDatos}</Text>
                </Table.Td>
              </Table.Tr>
            )}
            {data?.items.map((row) => (
              <Table.Tr key={row.id} opacity={row.is_active ? 1 : 0.6}>
                {config.columns.map((c) => (
                  <Table.Td key={c.label}>{c.render(row)}</Table.Td>
                ))}
                <Table.Td>
                  <ActiveBadge active={row.is_active} />
                </Table.Td>
                {canManage && (
                  <Table.Td>
                    <Menu shadow="md" position="bottom-end">
                      <Menu.Target>
                        <ActionIcon variant="subtle" aria-label={t.acciones}>
                          <IconDots size={16} />
                        </ActionIcon>
                      </Menu.Target>
                      <Menu.Dropdown>
                        <Menu.Item onClick={() => setEditing(row)}>{t.editar}</Menu.Item>
                        {config.rowActions
                          ?.filter((a) => !a.hidden?.(row))
                          .map((a) => (
                            <Menu.Item key={a.label} color={a.color} onClick={() => a.onClick(row)}>
                              {a.label}
                            </Menu.Item>
                          ))}
                        <Menu.Item
                          color={row.is_active ? "red" : "green"}
                          onClick={() => toggleActive.mutate(row)}
                        >
                          {row.is_active ? t.desactivar : t.activar}
                        </Menu.Item>
                      </Menu.Dropdown>
                    </Menu>
                  </Table.Td>
                )}
              </Table.Tr>
            ))}
          </Table.Tbody>
        </Table>
      </Table.ScrollContainer>

      {totalPages > 1 && <Pagination value={page} onChange={setPage} total={totalPages} />}

      <CatalogFormModal
        key={editing === "new" ? "new" : (editing?.id ?? "none")}
        config={config}
        row={editing}
        onClose={() => setEditing(null)}
        onDone={invalidate}
      />
    </Stack>
  );
}

function initialValues(fields: FieldDef[], row: Record<string, unknown> | null) {
  const values: Record<string, FieldValue> = {};
  for (const f of fields) {
    const v = row?.[f.name];
    if (f.type === "checkbox") values[f.name] = Boolean(v);
    else values[f.name] = v === null || v === undefined ? "" : String(v);
  }
  return values;
}

function CatalogFormModal<T extends { id: number; is_active: boolean }>({
  config,
  row,
  onClose,
  onDone,
}: {
  config: CatalogConfig<T>;
  row: T | "new" | null;
  onClose: () => void;
  onDone: () => void;
}) {
  const isNew = row === "new";
  const existing = row && row !== "new" ? row : null;
  const fields = config.fields.filter((f) => isNew || !f.createOnly);
  const [values, setValues] = useState(() =>
    initialValues(fields, existing as unknown as Record<string, unknown> | null),
  );
  const [error, setError] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: async () => {
      const payload = toPayload(fields, values);
      if (isNew) {
        // Create schemas don't accept nulls for omitted optional fields.
        for (const k of Object.keys(payload)) if (payload[k] === null) delete payload[k];
        return config.create(payload);
      }
      return config.update(existing!.id, payload);
    },
    onSuccess: (result) => {
      notifications.show({ message: isNew ? t.creado : t.actualizado, color: "green" });
      onDone();
      onClose();
      if (isNew) config.onCreated?.(result);
    },
    onError: (err) =>
      setError(err instanceof ApiError ? err.message : strings.common.errorGenerico),
  });

  const set = (name: string, value: FieldValue) => setValues((p) => ({ ...p, [name]: value }));

  return (
    <Modal
      opened={row !== null}
      onClose={onClose}
      title={isNew ? config.newLabel : `${t.editar}: ${config.title}`}
    >
      <form
        onSubmit={(e) => {
          e.preventDefault();
          setError(null);
          mutation.mutate();
        }}
      >
        <Stack gap="sm">
          {fields.map((f) => {
            const v = values[f.name];
            if (f.type === "checkbox") {
              return (
                <Checkbox
                  key={f.name}
                  label={f.label}
                  description={f.description}
                  checked={Boolean(v)}
                  onChange={(e) => set(f.name, e.currentTarget.checked)}
                />
              );
            }
            if (f.type === "select") {
              return (
                <Select
                  key={f.name}
                  label={f.label}
                  description={f.description}
                  data={f.options ?? []}
                  value={(v as string) || null}
                  onChange={(nv) => set(f.name, nv ?? "")}
                  required={f.required}
                  searchable
                  allowDeselect={false}
                />
              );
            }
            return (
              <TextInput
                key={f.name}
                label={f.label}
                description={f.description}
                value={v as string}
                inputMode={f.type === "text" ? undefined : "decimal"}
                onChange={(e) => set(f.name, e.currentTarget.value)}
                required={f.required}
              />
            );
          })}
          {error && <Text c="red">{error}</Text>}
          <Group justify="end" mt="sm">
            <Button variant="default" onClick={onClose}>
              {strings.common.cancelar}
            </Button>
            <Button type="submit" loading={mutation.isPending}>
              {strings.common.guardar}
            </Button>
          </Group>
        </Stack>
      </form>
    </Modal>
  );
}

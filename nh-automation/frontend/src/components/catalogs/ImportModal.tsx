import {
  Alert,
  Badge,
  Button,
  Checkbox,
  FileInput,
  Group,
  List,
  Modal,
  Radio,
  Select,
  Stack,
  Table,
  Text,
} from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { IconAlertTriangle, IconUpload } from "@tabler/icons-react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { ApiError } from "../../api/client";
import { importsApi } from "../../api/imports";
import type { ImportAction, ImportKind, ImportMode, ImportResult } from "../../api/types";
import { strings } from "../../i18n/strings";

const t = strings.imports;

const ACTION_COLOR: Record<ImportAction, string> = {
  create: "green",
  update: "blue",
  skip: "gray",
  error: "red",
};

/** Import from CSV/XLSX or the external catalog database (FR-CAT-7):
 * preview with per-row errors, then confirm. Nothing is saved while the
 * preview has errors -- the server re-validates on confirm anyway. */
export function ImportModal({
  kind,
  opened,
  onClose,
  onDone,
}: {
  kind: ImportKind;
  opened: boolean;
  onClose: () => void;
  onDone: () => void;
}) {
  const [source, setSource] = useState<string>("file");
  const [mode, setMode] = useState<ImportMode>("create_only");
  const [file, setFile] = useState<File | null>(null);
  const [result, setResult] = useState<ImportResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [onlyIssues, setOnlyIssues] = useState(false);

  const { data: sources } = useQuery({
    queryKey: ["import-sources", kind],
    queryFn: () => importsApi.sources(kind),
    enabled: opened,
  });

  const reset = () => {
    setResult(null);
    setError(null);
  };

  const onFail = (err: unknown) => {
    setResult(null);
    setError(err instanceof ApiError ? err.message : strings.common.errorGenerico);
  };

  const preview = useMutation({
    mutationFn: () => importsApi.preview(kind, source, mode, source === "file" ? file : null),
    onSuccess: (r) => {
      setError(null);
      setResult(r);
    },
    onError: onFail,
  });

  const confirm = useMutation({
    mutationFn: () => importsApi.confirm(kind, source, mode, source === "file" ? file : null),
    onSuccess: (r) => {
      const s = r.summary;
      notifications.show({
        message: `${t.exito} ${t.resumen.create}: ${s.create}, ${t.resumen.update}: ${s.update}, ${t.resumen.skip}: ${s.skip}.`,
        color: "green",
      });
      onDone();
      handleClose();
    },
    onError: onFail,
  });

  function handleClose() {
    reset();
    setFile(null);
    onClose();
  }

  const sourceOptions = sources?.sources.map((s) => ({
    value: s.name,
    label: s.available ? s.label : `${s.label} (${t.origenNoDisponible})`,
    disabled: !s.available,
  })) ?? [{ value: "file", label: "CSV / XLSX" }];

  const canPreview = source !== "file" || file !== null;
  const rows = result?.rows.filter((r) => !onlyIssues || r.errors.length || r.warnings.length);

  return (
    <Modal opened={opened} onClose={handleClose} title={t.title} size="90%">
      <Stack>
        <Group align="start" grow>
          <Select
            label={t.origen}
            data={sourceOptions}
            value={source}
            onChange={(v) => {
              setSource(v ?? "file");
              reset();
            }}
            allowDeselect={false}
          />
          <Radio.Group
            label={t.modo}
            value={mode}
            onChange={(v) => {
              setMode(v as ImportMode);
              reset();
            }}
          >
            <Stack gap={4} mt={4}>
              <Radio value="create_only" label={t.modoCrear} description={t.modoCrearDesc} />
              <Radio value="upsert" label={t.modoActualizar} description={t.modoActualizarDesc} />
            </Stack>
          </Radio.Group>
        </Group>

        {source === "file" && (
          <FileInput
            label={t.archivo}
            placeholder={t.archivoPlaceholder}
            accept=".csv,.xlsx,.txt"
            value={file}
            onChange={(f) => {
              setFile(f);
              reset();
            }}
            leftSection={<IconUpload size={16} />}
            clearable
          />
        )}
        <Text size="sm" c="dimmed">
          {t.ayudaExistencia}
        </Text>

        <Group>
          <Button
            variant="light"
            onClick={() => preview.mutate()}
            loading={preview.isPending}
            disabled={!canPreview}
          >
            {t.vistaPrevia}
          </Button>
          <Button
            onClick={() => confirm.mutate()}
            loading={confirm.isPending}
            disabled={!result || result.has_errors}
          >
            {t.confirmar}
          </Button>
        </Group>

        {error && (
          <Alert color="red" icon={<IconAlertTriangle size={16} />}>
            {error}
          </Alert>
        )}

        {result && (
          <>
            <Group gap="xs">
              {(Object.keys(t.resumen) as (keyof typeof t.resumen)[]).map((k) => (
                <Badge
                  key={k}
                  variant="light"
                  color={k === "error" && result.summary.error ? "red" : "gray"}
                >
                  {t.resumen[k]}: {result.summary[k]}
                </Badge>
              ))}
            </Group>

            {result.has_errors && (
              <Alert color="red" icon={<IconAlertTriangle size={16} />}>
                {result.global_errors.length > 0 && (
                  <List size="sm" mb="xs">
                    {result.global_errors.map((e) => (
                      <List.Item key={e}>{e}</List.Item>
                    ))}
                  </List>
                )}
                {t.hayErrores}
              </Alert>
            )}
            {result.unknown_columns.length > 0 && (
              <Text size="sm" c="dimmed">
                {t.columnasIgnoradas}: {result.unknown_columns.join(", ")}
              </Text>
            )}

            <Checkbox
              label={t.soloErrores}
              checked={onlyIssues}
              onChange={(e) => setOnlyIssues(e.currentTarget.checked)}
            />

            <Table.ScrollContainer minWidth={900} mah={420}>
              <Table striped withTableBorder stickyHeader>
                <Table.Thead>
                  <Table.Tr>
                    <Table.Th>{t.fila}</Table.Th>
                    <Table.Th>{t.accion}</Table.Th>
                    {result.fields.map((f) => (
                      <Table.Th key={f.name}>{f.label}</Table.Th>
                    ))}
                    <Table.Th>{t.observaciones}</Table.Th>
                  </Table.Tr>
                </Table.Thead>
                <Table.Tbody>
                  {rows?.map((r) => (
                    <Table.Tr
                      key={r.row_number}
                      bg={r.action === "error" ? "var(--mantine-color-red-light)" : undefined}
                    >
                      <Table.Td>{r.row_number}</Table.Td>
                      <Table.Td>
                        <Badge color={ACTION_COLOR[r.action]} variant="light">
                          {t.acciones[r.action]}
                        </Badge>
                      </Table.Td>
                      {result.fields.map((f) => (
                        <Table.Td key={f.name}>{r.values[f.name] ?? ""}</Table.Td>
                      ))}
                      <Table.Td>
                        {r.errors.map((e) => (
                          <Text key={e} size="sm" c="red">
                            {e}
                          </Text>
                        ))}
                        {r.warnings.map((w) => (
                          <Text key={w} size="sm" c="orange">
                            {w}
                          </Text>
                        ))}
                      </Table.Td>
                    </Table.Tr>
                  ))}
                </Table.Tbody>
              </Table>
            </Table.ScrollContainer>
          </>
        )}
      </Stack>
    </Modal>
  );
}

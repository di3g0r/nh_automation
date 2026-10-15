import {
  Button,
  Group,
  Modal,
  SegmentedControl,
  Select,
  Stack,
  Text,
  TextInput,
  Textarea,
} from "@mantine/core";
import { useDebouncedValue } from "@mantine/hooks";
import { notifications } from "@mantine/notifications";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { packagingApi, productsApi, sitesApi } from "../../api/catalogs";
import { ApiError } from "../../api/client";
import { inventoryApi } from "../../api/inventory";
import type { ItemType } from "../../api/types";
import { strings } from "../../i18n/strings";
import { adjustmentDelta, formatQuantity, formatSignedQuantity } from "../../utils/quantity";

const t = strings.inventory;

interface Option {
  value: string;
  label: string;
}

/** Active sites for new movements (FR-CAT-6), default site preselected. */
function useSiteOptions() {
  const { data } = useQuery({
    queryKey: ["sites", "active-for-select"],
    queryFn: () => sitesApi.list({ active: true, page_size: 500 }),
  });
  const options: Option[] = data?.items.map((s) => ({ value: String(s.id), label: s.name })) ?? [];
  const defaultId = data?.items.find((s) => s.is_default)?.id;
  return { options, defaultId: defaultId ? String(defaultId) : null };
}

/** Server-side search over active products or packaging items. */
function ItemPicker({
  itemType,
  value,
  onChange,
}: {
  itemType: ItemType;
  value: Option | null;
  onChange: (o: Option | null) => void;
}) {
  const [search, setSearch] = useState("");
  const [debounced] = useDebouncedValue(search, 250);
  const { data } = useQuery({
    queryKey: ["item-picker", itemType, debounced],
    queryFn: async (): Promise<Option[]> => {
      const params = { search: debounced || undefined, active: true, page_size: 50 };
      if (itemType === "product") {
        const r = await productsApi.list(params);
        return r.items.map((p) => ({ value: String(p.id), label: `${p.code} — ${p.name}` }));
      }
      const r = await packagingApi.list(params);
      return r.items.map((p) => ({ value: String(p.id), label: `${p.code} — ${p.description}` }));
    },
  });
  // Keep the selected option listed even when it falls outside the current search.
  const options = [...(data ?? [])];
  if (value && !options.some((o) => o.value === value.value)) options.unshift(value);

  return (
    <Select
      label={t.form.articulo}
      placeholder={t.form.buscarArticulo}
      data={options}
      value={value?.value ?? null}
      onChange={(v) => onChange(options.find((o) => o.value === v) ?? null)}
      searchable
      searchValue={search}
      onSearchChange={setSearch}
      filter={({ options: opts }) => opts}
      nothingFoundMessage={strings.common.sinDatos}
      required
    />
  );
}

function useMoveForm() {
  const sites = useSiteOptions();
  const [itemType, setItemType] = useState<ItemType>("product");
  const [item, setItem] = useState<Option | null>(null);
  const [siteId, setSiteId] = useState<string | null>(null);
  const site = siteId ?? sites.defaultId;
  return { sites, itemType, setItemType, item, setItem, site, setSiteId };
}

function MoveTargetFields({ form }: { form: ReturnType<typeof useMoveForm> }) {
  return (
    <>
      <SegmentedControl
        value={form.itemType}
        onChange={(v) => {
          form.setItemType(v as ItemType);
          form.setItem(null);
        }}
        data={[
          { value: "product", label: t.form.producto },
          { value: "packaging", label: t.form.material },
        ]}
      />
      <ItemPicker
        key={form.itemType}
        itemType={form.itemType}
        value={form.item}
        onChange={form.setItem}
      />
      <Select
        label={t.form.sitio}
        data={form.sites.options}
        value={form.site}
        onChange={form.setSiteId}
        allowDeselect={false}
        required
      />
    </>
  );
}

function useOnSaved(onClose: () => void, message: string) {
  const queryClient = useQueryClient();
  return () => {
    notifications.show({ message, color: "green" });
    queryClient.invalidateQueries({ queryKey: ["inventory"] });
    queryClient.invalidateQueries({ queryKey: ["inventory-alerts"] });
    onClose();
  };
}

const errorText = (err: unknown) =>
  err instanceof ApiError ? err.message : strings.common.errorGenerico;

/** FR-INV-2: Entrada (receipt). */
export function ReceiptModal({ opened, onClose }: { opened: boolean; onClose: () => void }) {
  const form = useMoveForm();
  const [quantity, setQuantity] = useState("");
  const [note, setNote] = useState("");
  const [error, setError] = useState<string | null>(null);
  const onSaved = useOnSaved(onClose, t.entradaOk);

  const mutation = useMutation({
    mutationFn: () =>
      inventoryApi.receipt({
        item_type: form.itemType,
        item_id: Number(form.item!.value),
        site_id: Number(form.site),
        quantity: quantity.trim(),
        note: note.trim() || undefined,
      }),
    onSuccess: onSaved,
    onError: (err) => setError(errorText(err)),
  });

  return (
    <Modal opened={opened} onClose={onClose} title={t.entradaTitulo}>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          setError(null);
          mutation.mutate();
        }}
      >
        <Stack gap="sm">
          <MoveTargetFields form={form} />
          <TextInput
            label={form.itemType === "product" ? t.form.cantidadLitros : t.form.cantidadUnidades}
            value={quantity}
            onChange={(e) => setQuantity(e.currentTarget.value)}
            inputMode="decimal"
            required
          />
          <Textarea
            label={t.form.nota}
            value={note}
            onChange={(e) => setNote(e.currentTarget.value)}
            autosize
            minRows={2}
          />
          {error && <Text c="red">{error}</Text>}
          <Group justify="end">
            <Button variant="default" onClick={onClose}>
              {strings.common.cancelar}
            </Button>
            <Button type="submit" loading={mutation.isPending} disabled={!form.item || !form.site}>
              {t.form.guardar}
            </Button>
          </Group>
        </Stack>
      </form>
    </Modal>
  );
}

/** FR-INV-3: Ajuste -- the user enters the counted quantity; the server computes the delta. */
export function AdjustmentModal({ opened, onClose }: { opened: boolean; onClose: () => void }) {
  const form = useMoveForm();
  const [counted, setCounted] = useState("");
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const onSaved = useOnSaved(onClose, t.ajusteOk);

  const { data: availability } = useQuery({
    queryKey: ["inventory", "availability", form.itemType, form.item?.value, form.site],
    queryFn: () =>
      inventoryApi.availability(form.itemType, Number(form.item!.value), Number(form.site)),
    enabled: Boolean(form.item && form.site),
  });
  const delta = availability ? adjustmentDelta(counted, availability.on_hand) : null;

  const mutation = useMutation({
    mutationFn: () =>
      inventoryApi.adjustment({
        item_type: form.itemType,
        item_id: Number(form.item!.value),
        site_id: Number(form.site),
        counted_quantity: counted.trim(),
        reason: reason.trim(),
      }),
    onSuccess: onSaved,
    onError: (err) => setError(errorText(err)),
  });

  return (
    <Modal opened={opened} onClose={onClose} title={t.ajusteTitulo}>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          setError(null);
          mutation.mutate();
        }}
      >
        <Stack gap="sm">
          <MoveTargetFields form={form} />
          {availability && (
            <Text size="sm">
              {t.form.existenciaActual}:{" "}
              <b>{formatQuantity(form.itemType, availability.on_hand)}</b>
            </Text>
          )}
          <TextInput
            label={t.form.cantidadContada}
            value={counted}
            onChange={(e) => setCounted(e.currentTarget.value)}
            inputMode="decimal"
            required
          />
          {delta !== null && (
            <Text size="sm" c={delta < 0 ? "red" : delta > 0 ? "green" : "dimmed"}>
              {t.form.diferencia}: {formatSignedQuantity(form.itemType, delta)}
            </Text>
          )}
          <Textarea
            label={t.form.motivo}
            value={reason}
            onChange={(e) => setReason(e.currentTarget.value)}
            autosize
            minRows={2}
            required
          />
          {error && <Text c="red">{error}</Text>}
          <Group justify="end">
            <Button variant="default" onClick={onClose}>
              {strings.common.cancelar}
            </Button>
            <Button
              type="submit"
              loading={mutation.isPending}
              disabled={!form.item || !form.site || !reason.trim()}
            >
              {t.form.guardar}
            </Button>
          </Group>
        </Stack>
      </form>
    </Modal>
  );
}

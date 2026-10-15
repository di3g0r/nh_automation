import { Select } from "@mantine/core";
import { useDebouncedValue } from "@mantine/hooks";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { productsApi } from "../../api/catalogs";
import type { Product } from "../../api/types";
import { strings } from "../../i18n/strings";

/** Server-side search over active products; keeps the selected product listed. */
export function ProductSelect({
  value,
  onChange,
  label,
  error,
  disabledIds = [],
  w,
  required,
  clearable = true,
}: {
  value: Product | null;
  onChange: (p: Product | null) => void;
  label?: string;
  error?: string | null;
  disabledIds?: number[];
  w?: number | string;
  required?: boolean;
  clearable?: boolean;
}) {
  const [search, setSearch] = useState("");
  const [debounced] = useDebouncedValue(search, 250);
  const { data } = useQuery({
    queryKey: ["product-select", debounced],
    queryFn: () =>
      productsApi.list({ search: debounced || undefined, active: true, page_size: 50 }),
  });
  const products = [...(data?.items ?? [])];
  if (value && !products.some((p) => p.id === value.id)) products.unshift(value);

  return (
    <Select
      label={label}
      placeholder={strings.orders.form.buscarProducto}
      data={products.map((p) => ({
        value: String(p.id),
        label: `${p.code} — ${p.name} (${p.presentation})`,
        disabled: disabledIds.includes(p.id) && p.id !== value?.id,
      }))}
      value={value ? String(value.id) : null}
      onChange={(v) => onChange(products.find((p) => String(p.id) === v) ?? null)}
      searchable
      searchValue={search}
      onSearchChange={setSearch}
      filter={({ options }) => options}
      nothingFoundMessage={strings.common.sinDatos}
      clearable={clearable}
      error={error}
      w={w}
      required={required}
    />
  );
}

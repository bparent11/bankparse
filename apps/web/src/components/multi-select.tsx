"use client";

import { Popover } from "@base-ui/react/popover";
import { Check, ChevronDown, Search } from "lucide-react";
import { useId, useState } from "react";

import { cn } from "@/lib/utils";

export type MultiOption = { value: string; label: string; hint?: string };

/**
 * Drop-down list with checkboxes: everything, several values, or everything but one (select all, then untick).
 * ``value`` null means "everything" (no filter); an empty array means nothing is selected.
 */
export function MultiSelect({
  label,
  allLabel,
  options,
  value,
  onChange,
  searchable = options.length > 8,
  className,
}: {
  /** What is filtered, used in the summary and for screen readers (e.g. "comptes"). */
  label: string;
  /** Summary when everything is selected (e.g. "Tous les comptes"). */
  allLabel: string;
  options: MultiOption[];
  value: string[] | null;
  onChange: (value: string[] | null) => void;
  searchable?: boolean;
  className?: string;
}) {
  const [search, setSearch] = useState("");
  const listId = useId();
  const all = options.map((o) => o.value);
  const selected = new Set(value ?? all);
  const isAll = value === null || all.every((v) => selected.has(v));

  // Back to null once everything is ticked again, so the filter disappears from the query.
  const commit = (next: Set<string>) => onChange(all.every((v) => next.has(v)) ? null : all.filter((v) => next.has(v)));
  const toggle = (v: string) => {
    const next = new Set(selected);
    if (next.has(v)) next.delete(v);
    else next.add(v);
    commit(next);
  };

  const summary = (): string => {
    if (isAll) return allLabel;
    if (selected.size === 0) return `Aucun (${label})`;
    const names = options.filter((o) => selected.has(o.value)).map((o) => o.label);
    if (names.length === 1) return names[0];
    const missing = options.filter((o) => !selected.has(o.value)).map((o) => o.label);
    if (missing.length === 1) return `Tout sauf ${missing[0]}`;
    return `${names.length} ${label}`;
  };

  const visible = search
    ? options.filter((o) => o.label.toLowerCase().includes(search.trim().toLowerCase()))
    : options;

  return (
    <Popover.Root onOpenChange={(open) => !open && setSearch("")}>
      <Popover.Trigger
        aria-label={`Filtrer les ${label} : ${summary()}`}
        className={cn(
          "flex h-8 w-full min-w-0 items-center justify-between gap-2 rounded-lg border border-input bg-transparent py-1 pr-2 pl-2.5 text-left text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 dark:bg-input/30",
          !isAll && "border-primary/60 bg-primary/5",
          className,
        )}
      >
        <span className="truncate">{summary()}</span>
        <ChevronDown className="size-4 shrink-0 text-muted-foreground" />
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Positioner sideOffset={4} align="start" className="isolate z-50">
          <Popover.Popup className="w-(--anchor-width) min-w-64 rounded-lg border bg-popover p-1 text-sm text-popover-foreground shadow-md outline-none">
            {searchable && (
              <div className="relative mb-1">
                <Search className="pointer-events-none absolute top-1/2 left-2 size-3.5 -translate-y-1/2 text-muted-foreground" />
                <input
                  aria-label={`Chercher parmi les ${label}`}
                  aria-controls={listId}
                  placeholder="Chercher…"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  className="h-7 w-full rounded-md bg-muted/60 pr-2 pl-7 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring/50"
                />
              </div>
            )}
            <div className="flex items-center justify-between gap-2 border-b px-2 pb-1 text-xs">
              <span className="text-muted-foreground">
                {isAll ? "Tout" : selected.size} / {options.length}
              </span>
              <span className="flex gap-3">
                <button type="button" className="font-medium text-primary hover:underline" onClick={() => onChange(null)}>
                  Tout
                </button>
                <button type="button" className="font-medium text-primary hover:underline" onClick={() => onChange([])}>
                  Aucun
                </button>
              </span>
            </div>
            <ul id={listId} className="max-h-72 overflow-y-auto py-1" aria-label={label}>
              {visible.map((o) => {
                const checked = selected.has(o.value);
                return (
                  <li key={o.value} className="group flex items-center rounded-md hover:bg-muted">
                    <label className="flex min-w-0 flex-1 cursor-pointer items-center gap-2 px-2 py-1.5">
                      <input
                        type="checkbox"
                        className="peer sr-only"
                        checked={checked}
                        onChange={() => toggle(o.value)}
                      />
                      <span
                        aria-hidden
                        className={cn(
                          "flex size-4 shrink-0 items-center justify-center rounded border border-input peer-focus-visible:ring-2 peer-focus-visible:ring-ring/50",
                          checked && "border-primary bg-primary text-primary-foreground",
                        )}
                      >
                        {checked && <Check className="size-3" />}
                      </span>
                      <span className="truncate">{o.label}</span>
                      {o.hint && <span className="ml-auto shrink-0 text-xs text-muted-foreground">{o.hint}</span>}
                    </label>
                    <button
                      type="button"
                      aria-label={`Seulement ${o.label}`}
                      className="mr-1 rounded px-1.5 py-0.5 text-xs text-primary opacity-0 group-hover:opacity-100 hover:underline focus-visible:opacity-100"
                      onClick={() => onChange(all.length === 1 ? null : [o.value])}
                    >
                      seulement
                    </button>
                  </li>
                );
              })}
              {visible.length === 0 && <li className="px-2 py-1.5 text-muted-foreground">Aucun résultat</li>}
            </ul>
          </Popover.Popup>
        </Popover.Positioner>
      </Popover.Portal>
    </Popover.Root>
  );
}

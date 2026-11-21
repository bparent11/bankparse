"use client";

import { useMutation } from "@tanstack/react-query";
import {
  ArrowDown,
  ArrowUp,
  ArrowUpDown,
  Check,
  CheckCheck,
  ChevronLeft,
  ChevronRight,
  Download,
  ListOrdered,
  Search,
  SlidersHorizontal,
  X,
} from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { Dialog as DialogPrimitive } from "@base-ui/react/dialog";

import { Amount, EmptyState, ErrorMessage, PageHeader, Stat } from "@/components/common";
import { MultiSelect, multiSummary, type MultiOption } from "@/components/multi-select";
import { NativeSelect } from "@/components/native-select";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api, toQueryString, unwrap, type Transaction, type TransactionQuery } from "@/lib/api";
import { categoryColor } from "@/lib/category-color";
import { BANK_LABELS, formatShortDate } from "@/lib/format";
import { useAccounts, useCategories, useInvalidateData, useTransactions } from "@/lib/queries";
import { useSpace } from "@/lib/space";
import { cn } from "@/lib/utils";

import { CategorizeCard } from "./categorize-card";
import { CategoryDialog } from "./category-dialog";

type Sort = NonNullable<TransactionQuery["sort"]>;
/** Multiple-choice filters: null = everything (no filter), [] = nothing selected. */
type Multi = string[] | null;
type Filters = {
  q: string;
  accounts: Multi; // account ids
  banks: Multi; // bank codes
  categories: Multi; // category names, NONE = without category
  sources: Multi; // who chose the category (see SOURCES)
  directions: Multi; // "credit" | "debit"
  dateFrom: string;
  dateTo: string;
  min: string;
  max: string;
};

const NONE = "__none__";

const SOURCES: MultiOption[] = [
  { value: "user", label: "Choisie par vous" },
  { value: "rule", label: "Règle « similaires »" },
  { value: "llm", label: "Proposée par l'IA (à vérifier)" },
  { value: "validated", label: "Proposée par l'IA, validée" },
  { value: "none", label: "Pas encore catégorisée" },
];
const DIRECTIONS: MultiOption[] = [
  { value: "credit", label: "Crédits" },
  { value: "debit", label: "Débits" },
];

const CUSTOM = "custom";
const PERIODS = [
  { value: "all", label: "Toute la période" },
  { value: "month", label: "Ce mois-ci" },
  { value: "last-month", label: "Le mois dernier" },
  { value: "3m", label: "3 derniers mois" },
  { value: "12m", label: "12 derniers mois" },
  { value: "year", label: "Cette année" },
  { value: "last-year", label: "L'année dernière" },
];

/** [from, to] as yyyy-mm-dd (local time) for a period preset; empty strings = no bound. */
function periodRange(value: string): [string, string] {
  const iso = (d: Date) =>
    `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
  const now = new Date();
  const y = now.getFullYear();
  const m = now.getMonth();
  switch (value) {
    case "month":
      return [iso(new Date(y, m, 1)), ""];
    case "last-month":
      return [iso(new Date(y, m - 1, 1)), iso(new Date(y, m, 0))];
    case "3m":
      return [iso(new Date(y, m - 2, 1)), ""];
    case "12m":
      return [iso(new Date(y, m - 11, 1)), ""];
    case "year":
      return [iso(new Date(y, 0, 1)), ""];
    case "last-year":
      return [iso(new Date(y - 1, 0, 1)), iso(new Date(y - 1, 11, 31))];
    default:
      return ["", ""];
  }
}

const PAGE_SIZE = 50;
const EMPTY: Filters = {
  q: "",
  accounts: null,
  banks: null,
  categories: null,
  sources: null,
  directions: null,
  dateFrom: "",
  dateTo: "",
  min: "",
  max: "",
};

function useDebounced<T>(value: T, delay = 300): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const id = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(id);
  }, [value, delay]);
  return debounced;
}

/** Filters start afresh when another space is chosen (its accounts are not the same). */
export function OperationsView() {
  const { spaceId } = useSpace();
  return <SpaceOperations key={spaceId ?? 0} spaceId={spaceId} />;
}

function SpaceOperations({ spaceId }: { spaceId: number | undefined }) {
  const searchParams = useSearchParams();
  const [filters, setFilters] = useState<Filters>({
    ...EMPTY,
    accounts: searchParams.get("account") ? [searchParams.get("account")!] : null,
  });
  const [sort, setSort] = useState<Sort>("operation_date");
  const [order, setOrder] = useState<"asc" | "desc">("desc");
  const [page, setPage] = useState(1);
  const debounced = useDebounced(filters);

  const accounts = useAccounts();
  const categories = useCategories();
  const [editing, setEditing] = useState<Transaction | null>(null);
  const d = debounced;
  // A list with nothing ticked matches no operation: the query is not even sent.
  const nothingSelected = [d.accounts, d.banks, d.categories, d.sources, d.directions].some((m) => m?.length === 0);
  const query: TransactionQuery = {
    space_id: spaceId,
    q: d.q || undefined,
    account_id: d.accounts?.map(Number),
    bank_code: d.banks ?? undefined,
    category: d.categories ?? undefined,
    source: (d.sources as TransactionQuery["source"]) ?? undefined,
    direction: d.directions?.length === 1 ? (d.directions[0] as "credit" | "debit") : undefined,
    date_from: d.dateFrom || undefined,
    date_to: d.dateTo || undefined,
    min_amount: d.min !== "" ? Number(d.min) : undefined,
    max_amount: d.max !== "" ? Number(d.max) : undefined,
    sort,
    order,
    page,
    page_size: PAGE_SIZE,
  };
  const transactions = useTransactions(query, !nothingSelected);
  const { error, isFetching } = transactions;
  const data = nothingSelected ? undefined : transactions.data;
  const isPending = !nothingSelected && transactions.isPending;
  const reviewOnly = filters.sources?.length === 1 && filters.sources[0] === "llm";

  const accountOptions: MultiOption[] = (accounts.data ?? []).map((a) => ({
    value: String(a.id),
    label: a.label,
    hint: a.bank_code,
  }));
  const bankOptions: MultiOption[] = [...new Set((accounts.data ?? []).map((a) => a.bank_code))].map((code) => ({
    value: code,
    label: BANK_LABELS[code] ?? code,
  }));
  const categoryOptions: MultiOption[] = [
    { value: NONE, label: "Sans catégorie" },
    ...(categories.data ?? []).map((c) => ({
      value: c.name,
      label: c.name,
      hint: String(c.transaction_count),
    })),
  ];
  const invalidate = useInvalidateData();

  const validate = useMutation({
    mutationFn: ({ id, validated }: { id: number; validated: boolean }) =>
      unwrap(
        api.POST("/api/transactions/{transaction_id}/validation", {
          params: { path: { transaction_id: id } },
          body: { validated },
        }),
      ),
    onSuccess: () => invalidate(),
    onError: (e) => toast.error(e.message),
  });
  const validateAll = useMutation({
    mutationFn: () =>
      unwrap(
        api.POST("/api/transactions/validation", {
          params: {
            query: {
              ...query,
              page: undefined,
              page_size: undefined,
              sort: undefined,
              order: undefined,
            },
          },
        }),
      ),
    onSuccess: async (r) => {
      await invalidate();
      toast.success(`${r.updated} catégorie${r.updated > 1 ? "s" : ""} validée${r.updated > 1 ? "s" : ""}`);
    },
    onError: (e) => toast.error(e.message),
  });
  const onValidate = (t: Transaction) => validate.mutate({ id: t.id, validated: t.category_source !== "validated" });

  const setFilter = <K extends keyof Filters>(key: K, value: Filters[K]) => {
    setFilters((f) => ({ ...f, [key]: value }));
    setPage(1);
  };
  const toggleSort = (field: Sort) => {
    if (sort === field) setOrder(order === "asc" ? "desc" : "asc");
    else {
      setSort(field);
      setOrder(field === "label" || field === "account" ? "asc" : "desc");
    }
    setPage(1);
  };

  const hasFilters = JSON.stringify(filters) !== JSON.stringify(EMPTY);
  const clearAll = () => {
    setFilters(EMPTY);
    setPage(1);
  };
  const [panelOpen, setPanelOpen] = useState(false);
  const period =
    PERIODS.find((p) => {
      const [from, to] = periodRange(p.value);
      return from === filters.dateFrom && to === filters.dateTo;
    })?.value ?? CUSTOM;

  // One removable chip per active filter (the period has its own selector, unless dates were typed by hand).
  const chips: {
    key: string;
    label: string;
    value: string;
    clear: () => void;
  }[] = [];
  const multiChip = (key: keyof Filters, label: string, options: MultiOption[], name: string, all: string) => {
    const value = filters[key];
    if (Array.isArray(value))
      chips.push({
        key,
        label,
        value: multiSummary(options, value, name, all),
        clear: () => setFilter(key, null),
      });
  };
  multiChip("accounts", "Comptes", accountOptions, "comptes", "Tous les comptes");
  multiChip("banks", "Banques", bankOptions, "banques", "Toutes les banques");
  multiChip("categories", "Catégories", categoryOptions, "catégories", "Toutes les catégories");
  multiChip("sources", "Statut", SOURCES, "statuts", "Tous les statuts");
  multiChip("directions", "Sens", DIRECTIONS, "sens", "Crédits et débits");
  if (filters.min !== "" || filters.max !== "")
    chips.push({
      key: "amount",
      label: "Montant",
      value:
        filters.min !== "" && filters.max !== ""
          ? `${filters.min} € à ${filters.max} €`
          : filters.min !== ""
            ? `≥ ${filters.min} €`
            : `≤ ${filters.max} €`,
      clear: () => setFilters((f) => ({ ...f, min: "", max: "" })),
    });
  if (period === CUSTOM)
    chips.push({
      key: "dates",
      label: "Dates",
      value:
        filters.dateFrom && filters.dateTo
          ? `du ${formatShortDate(filters.dateFrom)} au ${formatShortDate(filters.dateTo)}`
          : filters.dateFrom
            ? `depuis le ${formatShortDate(filters.dateFrom)}`
            : `jusqu'au ${formatShortDate(filters.dateTo)}`,
      clear: () => setFilters((f) => ({ ...f, dateFrom: "", dateTo: "" })),
    });
  const pages = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1;
  const exportQs = toQueryString({
    ...query,
    page: undefined,
    page_size: undefined,
    order: "asc",
  });

  return (
    <>
      <PageHeader
        title="Opérations"
        description={hasFilters ? "Opérations correspondant à vos filtres" : "Toutes vos opérations importées"}
        actions={(["csv", "xlsx", "json"] as const).map((format) => (
          <Button
            key={format}
            variant="outline"
            size="sm"
            nativeButton={false}
            render={<a href={`/api/transactions/export?${exportQs}&format=${format}`} download />}
          >
            <Download /> {format === "xlsx" ? "Excel" : format.toUpperCase()}
          </Button>
        ))}
      />

      <div className="mb-4 grid gap-3 sm:grid-cols-3">
        <Stat label="Opérations">
          {data ? data.total.toLocaleString("fr-FR") : nothingSelected ? "0" : <Skeleton className="mt-1 h-5 w-16" />}
        </Stat>
        <Stat label="Entrées">
          {data ? <Amount value={data.total_credit} /> : <Skeleton className="mt-1 h-5 w-24" />}
        </Stat>
        <Stat label="Sorties">
          {data ? <Amount value={data.total_debit} /> : <Skeleton className="mt-1 h-5 w-24" />}
        </Stat>
      </div>

      <CategorizeCard />

      <div className="mb-3 flex flex-wrap gap-2">
        <div className="relative min-w-56 flex-1">
          <Search className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            aria-label="Rechercher dans les libellés"
            placeholder="Rechercher un libellé (ex : loyer, carte…)"
            value={filters.q}
            onChange={(e) => setFilter("q", e.target.value)}
            className="bg-card pl-8"
          />
        </div>
        <NativeSelect
          aria-label="Période"
          className="w-auto bg-card"
          value={period}
          onChange={(e) => {
            const range = e.target.value === CUSTOM ? null : periodRange(e.target.value);
            if (range)
              setFilters((f) => ({
                ...f,
                dateFrom: range[0],
                dateTo: range[1],
              }));
            else setPanelOpen(true);
            setPage(1);
          }}
        >
          {PERIODS.map((p) => (
            <option key={p.value} value={p.value}>
              {p.label}
            </option>
          ))}
          <option value={CUSTOM}>{period === CUSTOM ? "Dates choisies" : "Choisir des dates…"}</option>
        </NativeSelect>
        <Button variant={chips.length ? "default" : "outline"} onClick={() => setPanelOpen(true)}>
          <SlidersHorizontal /> Filtres
          {chips.length > 0 && (
            <span className="rounded-full bg-primary-foreground px-1.5 text-xs font-semibold text-primary">
              {chips.length}
            </span>
          )}
        </Button>
      </div>

      {(chips.length > 0 || hasFilters) && (
        <div className="mb-3 flex flex-wrap items-center gap-1.5">
          {chips.map((c) => (
            <span
              key={c.key}
              className="inline-flex items-center gap-1 rounded-full bg-accent py-0.5 pr-1 pl-2.5 text-xs text-accent-foreground"
            >
              <span className="opacity-75">{c.label} :</span> {c.value}
              <button
                type="button"
                aria-label={`Retirer le filtre ${c.label}`}
                onClick={c.clear}
                className="flex size-4 items-center justify-center rounded-full hover:bg-accent-foreground/15"
              >
                <X className="size-3" />
              </button>
            </span>
          ))}
          {hasFilters && (
            <button type="button" onClick={clearAll} className="text-xs text-primary underline underline-offset-4">
              Tout effacer
            </button>
          )}
        </div>
      )}

      <FilterPanel
        open={panelOpen}
        onOpenChange={setPanelOpen}
        filters={filters}
        setFilter={setFilter}
        onClear={clearAll}
        total={data?.total}
        accountOptions={accountOptions}
        bankOptions={bankOptions}
        categoryOptions={categoryOptions}
      />

      <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            className="size-4 accent-primary"
            checked={reviewOnly}
            onChange={(e) => setFilter("sources", e.target.checked ? ["llm"] : null)}
          />
          À vérifier seulement{" "}
          <span className="text-muted-foreground">(proposées par l&apos;IA, pas encore validées)</span>
        </label>
        {reviewOnly && data && data.total > 0 && (
          <Button
            size="sm"
            variant="outline"
            disabled={validateAll.isPending}
            onClick={() => {
              if (window.confirm(`Valider les ${data.total} catégories affichées par ces filtres ?`))
                validateAll.mutate();
            }}
          >
            <CheckCheck /> Valider ces {data.total} opération
            {data.total > 1 ? "s" : ""}
          </Button>
        )}
      </div>

      {nothingSelected ? (
        <EmptyState icon={ListOrdered} title="Rien n'est coché dans un des filtres">
          Cochez au moins une valeur, ou cliquez sur « Tout » dans la liste.
        </EmptyState>
      ) : error ? (
        <ErrorMessage error={error} />
      ) : isPending || !data ? (
        <Skeleton className="h-96 w-full" />
      ) : data.total === 0 ? (
        <EmptyState
          icon={ListOrdered}
          title={hasFilters ? "Aucune opération ne correspond aux filtres" : "Aucune opération"}
        >
          {!hasFilters && (
            <>
              Commencez par{" "}
              <Link href="/import" className="underline underline-offset-4">
                importer des relevés
              </Link>
              .
            </>
          )}
        </EmptyState>
      ) : (
        <>
          <div className={cn("rounded-xl border bg-card shadow-xs transition-opacity", isFetching && "opacity-60")}>
            <Table>
              <TableHeader>
                <TableRow>
                  <SortHead field="operation_date" sort={sort} order={order} onSort={toggleSort} className="w-28">
                    Date
                  </SortHead>
                  <SortHead
                    field="account"
                    sort={sort}
                    order={order}
                    onSort={toggleSort}
                    className="hidden md:table-cell"
                  >
                    Compte
                  </SortHead>
                  <SortHead field="label" sort={sort} order={order} onSort={toggleSort}>
                    Libellé
                  </SortHead>
                  <TableHead className="hidden sm:table-cell">Catégorie</TableHead>
                  <SortHead field="amount" sort={sort} order={order} onSort={toggleSort} className="text-right">
                    Montant
                  </SortHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.items.map((t) => (
                  <TableRow key={t.id}>
                    <TableCell className="font-mono text-xs tabular-nums text-muted-foreground">
                      {formatShortDate(t.operation_date)}
                    </TableCell>
                    <TableCell
                      className="hidden max-w-40 truncate text-muted-foreground md:table-cell"
                      title={t.account_label}
                    >
                      {t.account_label}
                    </TableCell>
                    <TableCell className="max-w-0 w-full">
                      <p className="truncate" title={t.label}>
                        {t.label}
                      </p>
                      <p className="truncate text-xs text-muted-foreground md:hidden">{t.account_label}</p>
                      <div className="mt-1 sm:hidden">
                        <CategoryButton tx={t} onClick={() => setEditing(t)} onValidate={() => onValidate(t)} />
                      </div>
                    </TableCell>
                    <TableCell className="hidden sm:table-cell">
                      <CategoryButton tx={t} onClick={() => setEditing(t)} onValidate={() => onValidate(t)} />
                    </TableCell>
                    <TableCell className="text-right">
                      <Amount value={t.amount} />
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
          <div className="mt-4 flex items-center justify-between text-sm text-muted-foreground">
            <span>
              Page {page} / {pages}
            </span>
            <div className="flex gap-2">
              <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage(page - 1)}>
                <ChevronLeft /> Précédent
              </Button>
              <Button variant="outline" size="sm" disabled={page >= pages} onClick={() => setPage(page + 1)}>
                Suivant <ChevronRight />
              </Button>
            </div>
          </div>
        </>
      )}
      <CategoryDialog tx={editing} onClose={() => setEditing(null)} />
    </>
  );
}

/** Side panel holding every filter, grouped by question (where, what, how much, when). */
function FilterPanel({
  open,
  onOpenChange,
  filters,
  setFilter,
  onClear,
  total,
  accountOptions,
  bankOptions,
  categoryOptions,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  filters: Filters;
  setFilter: <K extends keyof Filters>(key: K, value: Filters[K]) => void;
  onClear: () => void;
  total: number | undefined;
  accountOptions: MultiOption[];
  bankOptions: MultiOption[];
  categoryOptions: MultiOption[];
}) {
  const direction =
    filters.directions === null ? "all" : filters.directions.length === 1 ? filters.directions[0] : "none";
  return (
    <DialogPrimitive.Root open={open} onOpenChange={onOpenChange}>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Backdrop className="fixed inset-0 z-50 bg-black/20 supports-backdrop-filter:backdrop-blur-[2px] data-open:animate-in data-open:fade-in-0 data-closed:animate-out data-closed:fade-out-0" />
        <DialogPrimitive.Popup className="fixed inset-y-0 right-0 z-50 flex w-full max-w-sm flex-col border-l bg-popover text-sm text-popover-foreground shadow-2xl outline-none data-open:animate-in data-open:slide-in-from-right data-closed:animate-out data-closed:slide-out-to-right">
          <div className="flex items-center justify-between border-b px-5 py-4">
            <DialogPrimitive.Title className="text-base font-semibold">Filtres</DialogPrimitive.Title>
            <DialogPrimitive.Close render={<Button variant="ghost" size="icon-sm" aria-label="Fermer les filtres" />}>
              <X />
            </DialogPrimitive.Close>
          </div>
          <div className="flex-1 space-y-6 overflow-y-auto px-5 py-5">
            <PanelGroup title="Où">
              <PanelField label="Comptes">
                <MultiSelect
                  label="comptes"
                  allLabel="Tous les comptes"
                  options={accountOptions}
                  value={filters.accounts}
                  onChange={(v) => setFilter("accounts", v)}
                />
              </PanelField>
              <PanelField label="Banques">
                <MultiSelect
                  label="banques"
                  allLabel="Toutes les banques"
                  options={bankOptions}
                  value={filters.banks}
                  onChange={(v) => setFilter("banks", v)}
                />
              </PanelField>
            </PanelGroup>
            <PanelGroup title="Quoi">
              <PanelField label="Catégories">
                <MultiSelect
                  label="catégories"
                  allLabel="Toutes les catégories"
                  options={categoryOptions}
                  value={filters.categories}
                  onChange={(v) => setFilter("categories", v)}
                />
              </PanelField>
              <PanelField label="Statut de la catégorie">
                <MultiSelect
                  label="statuts"
                  allLabel="Tous les statuts"
                  options={SOURCES}
                  value={filters.sources}
                  onChange={(v) => setFilter("sources", v)}
                />
              </PanelField>
            </PanelGroup>
            <PanelGroup title="Combien">
              <div role="radiogroup" aria-label="Sens" className="flex overflow-hidden rounded-lg border">
                {[
                  { value: "all", label: "Tout", set: null },
                  { value: "credit", label: "Crédits", set: ["credit"] },
                  { value: "debit", label: "Débits", set: ["debit"] },
                ].map((o) => (
                  <button
                    key={o.value}
                    type="button"
                    role="radio"
                    aria-checked={direction === o.value}
                    onClick={() => setFilter("directions", o.set)}
                    className={cn(
                      "flex-1 py-1.5 text-sm transition-colors hover:bg-muted",
                      direction === o.value && "bg-accent font-medium text-accent-foreground hover:bg-accent",
                    )}
                  >
                    {o.label}
                  </button>
                ))}
              </div>
              <div className="grid grid-cols-2 gap-2">
                <PanelField label="Montant min (€)">
                  <Input
                    aria-label="Montant minimum"
                    type="number"
                    inputMode="decimal"
                    value={filters.min}
                    onChange={(e) => setFilter("min", e.target.value)}
                  />
                </PanelField>
                <PanelField label="Montant max (€)">
                  <Input
                    aria-label="Montant maximum"
                    type="number"
                    inputMode="decimal"
                    value={filters.max}
                    onChange={(e) => setFilter("max", e.target.value)}
                  />
                </PanelField>
              </div>
              <p className="text-xs text-muted-foreground">
                Les débits sont négatifs : « max −100 » garde les dépenses de plus de 100 €.
              </p>
            </PanelGroup>
            <PanelGroup title="Quand">
              <div className="grid grid-cols-2 gap-2">
                <PanelField label="Du">
                  <Input
                    type="date"
                    aria-label="Date de début"
                    value={filters.dateFrom}
                    onChange={(e) => setFilter("dateFrom", e.target.value)}
                  />
                </PanelField>
                <PanelField label="Au">
                  <Input
                    type="date"
                    aria-label="Date de fin"
                    value={filters.dateTo}
                    onChange={(e) => setFilter("dateTo", e.target.value)}
                  />
                </PanelField>
              </div>
            </PanelGroup>
          </div>
          <div className="flex items-center justify-between gap-2 border-t px-5 py-4">
            <button type="button" onClick={onClear} className="text-sm text-primary underline underline-offset-4">
              Tout effacer
            </button>
            <DialogPrimitive.Close render={<Button />}>
              {total === undefined
                ? "Voir les opérations"
                : `Voir ${total.toLocaleString("fr-FR")} opération${total > 1 ? "s" : ""}`}
            </DialogPrimitive.Close>
          </div>
        </DialogPrimitive.Popup>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
}

function PanelGroup({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="space-y-2.5">
      <h3 className="text-[11px] font-semibold tracking-wider text-muted-foreground uppercase">{title}</h3>
      {children}
    </section>
  );
}

function PanelField({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div role="group" aria-label={label} className="grid gap-1">
      <span className="text-xs text-muted-foreground">{label}</span>
      {children}
    </div>
  );
}

const SOURCE_LABELS: Record<string, string> = {
  user: "choisie par vous",
  rule: "reprise d'une de vos corrections",
  memory: "proposée par l'IA (ancienne version)",
  llm: "proposée par l'IA",
  validated: "proposée par l'IA et validée par vous",
};

function CategoryButton({ tx, onClick, onValidate }: { tx: Transaction; onClick: () => void; onValidate: () => void }) {
  const fromAi = tx.category_source === "llm" || tx.category_source === "memory";
  const validated = tx.category_source === "validated";
  const model = tx.category_model ? ` par ${tx.category_model}` : "";
  const source = fromAi
    ? `proposée${model}`
    : validated
      ? `proposée${model}, validée par vous`
      : tx.category_source
        ? SOURCE_LABELS[tx.category_source]
        : undefined;
  return (
    <span className="inline-flex items-center gap-1">
      <button
        type="button"
        onClick={onClick}
        title={
          tx.category ? `Catégorie ${source ? `(${source})` : ""} — cliquer pour modifier` : "Choisir une catégorie"
        }
        style={
          tx.category && tx.category !== "Inconnu"
            ? ({ "--c": categoryColor(tx.category) } as React.CSSProperties)
            : undefined
        }
        className={cn(
          "inline-flex max-w-44 items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs transition-[filter] hover:brightness-95 dark:hover:brightness-125",
          !tx.category && "border-dashed text-muted-foreground hover:bg-muted",
          tx.category === "Inconnu" && "border-amber-500/40 bg-amber-500/10 text-amber-700 dark:text-amber-300",
          tx.category && tx.category !== "Inconnu" && "category-chip",
          (tx.category_source === "user" || tx.category_source === "rule" || validated) && "font-medium",
          fromAi && "border-dashed",
        )}
      >
        {tx.category && tx.category !== "Inconnu" && (
          <span aria-hidden className="category-dot size-1.5 shrink-0 rounded-full" />
        )}
        <span className="truncate">{tx.category ?? "À classer"}</span>
      </button>
      {(fromAi || validated) && (
        <button
          type="button"
          onClick={onValidate}
          aria-pressed={validated}
          aria-label={validated ? "Annuler la validation" : "Valider la catégorie proposée par l'IA"}
          title={
            validated
              ? "Validée : ne sera plus jamais repassée à l'IA (cliquer pour annuler)"
              : "Valider cette catégorie : elle ne sera plus repassée à l'IA"
          }
          className={cn(
            "inline-flex size-5 shrink-0 items-center justify-center rounded-md border transition-colors",
            validated
              ? "border-transparent bg-positive text-white hover:opacity-80"
              : "border-dashed text-muted-foreground hover:border-solid hover:bg-muted hover:text-foreground",
          )}
        >
          <Check className="size-3.5" />
        </button>
      )}
    </span>
  );
}

function SortHead({
  field,
  sort,
  order,
  onSort,
  className,
  children,
}: {
  field: Sort;
  sort: Sort;
  order: "asc" | "desc";
  onSort: (field: Sort) => void;
  className?: string;
  children: React.ReactNode;
}) {
  const active = sort === field;
  const Icon = !active ? ArrowUpDown : order === "asc" ? ArrowUp : ArrowDown;
  return (
    <TableHead className={className} aria-sort={active ? (order === "asc" ? "ascending" : "descending") : "none"}>
      <button
        type="button"
        onClick={() => onSort(field)}
        className={cn(
          "inline-flex items-center gap-1 hover:text-foreground",
          className?.includes("text-right") && "flex-row-reverse",
          active ? "text-foreground" : "text-muted-foreground",
        )}
      >
        {children}
        <Icon className="size-3.5" />
      </button>
    </TableHead>
  );
}

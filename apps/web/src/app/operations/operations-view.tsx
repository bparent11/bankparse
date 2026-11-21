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
  X,
} from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { Amount, EmptyState, ErrorMessage, PageHeader } from "@/components/common";
import { NativeSelect } from "@/components/native-select";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api, toQueryString, unwrap, type Transaction, type TransactionQuery } from "@/lib/api";
import { formatShortDate } from "@/lib/format";
import { useAccounts, useCategories, useInvalidateData, useTransactions } from "@/lib/queries";
import { useSpace } from "@/lib/space";
import { cn } from "@/lib/utils";

import { CategorizeCard } from "./categorize-card";
import { CategoryDialog } from "./category-dialog";

type Sort = NonNullable<TransactionQuery["sort"]>;
type Filters = {
  q: string;
  account: string;
  direction: "" | "debit" | "credit";
  dateFrom: string;
  dateTo: string;
  min: string;
  max: string;
  category: string; // "" = all, NONE = uncategorized, otherwise a category name
  review: boolean; // only the categories proposed by the AI and not validated yet
};

const NONE = "__none__";

const PAGE_SIZE = 50;
const EMPTY: Filters = {
  q: "",
  account: "",
  direction: "",
  dateFrom: "",
  dateTo: "",
  min: "",
  max: "",
  category: "",
  review: false,
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
    account: searchParams.get("account") ?? "",
  });
  const [sort, setSort] = useState<Sort>("operation_date");
  const [order, setOrder] = useState<"asc" | "desc">("desc");
  const [page, setPage] = useState(1);
  const debounced = useDebounced(filters);

  const accounts = useAccounts();
  const categories = useCategories();
  const [editing, setEditing] = useState<Transaction | null>(null);
  const query: TransactionQuery = {
    space_id: spaceId,
    q: debounced.q || undefined,
    account_id: debounced.account ? [Number(debounced.account)] : undefined,
    direction: debounced.direction || undefined,
    date_from: debounced.dateFrom || undefined,
    date_to: debounced.dateTo || undefined,
    min_amount: debounced.min !== "" ? Number(debounced.min) : undefined,
    max_amount: debounced.max !== "" ? Number(debounced.max) : undefined,
    category: debounced.category && debounced.category !== NONE ? debounced.category : undefined,
    uncategorized: debounced.category === NONE ? true : undefined,
    to_review: debounced.review ? true : undefined,
    sort,
    order,
    page,
    page_size: PAGE_SIZE,
  };
  const { data, error, isPending, isFetching } = useTransactions(query);
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
        description={
          data ? (
            <>
              {data.total.toLocaleString("fr-FR")} opération
              {data.total > 1 ? "s" : ""} · crédits <Amount value={data.total_credit} /> · débits{" "}
              <Amount value={data.total_debit} />
            </>
          ) : (
            "Toutes vos opérations importées"
          )
        }
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

      <CategorizeCard />

      <div className="mb-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
        <div className="relative sm:col-span-2">
          <Search className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            aria-label="Rechercher dans les libellés"
            placeholder="Rechercher un libellé (ex : loyer, carte…)"
            value={filters.q}
            onChange={(e) => setFilter("q", e.target.value)}
            className="pl-8"
          />
        </div>
        <NativeSelect
          aria-label="Compte"
          value={filters.account}
          onChange={(e) => setFilter("account", e.target.value)}
        >
          <option value="">Tous les comptes</option>
          {accounts.data?.map((a) => (
            <option key={a.id} value={a.id}>
              {a.label} ({a.bank_code})
            </option>
          ))}
        </NativeSelect>
        <NativeSelect
          aria-label="Sens"
          value={filters.direction}
          onChange={(e) => setFilter("direction", e.target.value as Filters["direction"])}
        >
          <option value="">Crédits et débits</option>
          <option value="credit">Crédits uniquement</option>
          <option value="debit">Débits uniquement</option>
        </NativeSelect>
        <NativeSelect
          aria-label="Catégorie"
          value={filters.category}
          onChange={(e) => setFilter("category", e.target.value)}
        >
          <option value="">Toutes les catégories</option>
          <option value={NONE}>Non catégorisé</option>
          {categories.data?.map((c) => (
            <option key={c.id} value={c.name}>
              {c.name} ({c.transaction_count})
            </option>
          ))}
        </NativeSelect>
        <label className="flex items-center gap-2 text-sm text-muted-foreground">
          Du
          <Input type="date" value={filters.dateFrom} onChange={(e) => setFilter("dateFrom", e.target.value)} />
        </label>
        <label className="flex items-center gap-2 text-sm text-muted-foreground">
          au
          <Input type="date" value={filters.dateTo} onChange={(e) => setFilter("dateTo", e.target.value)} />
        </label>
        <Input
          type="number"
          inputMode="decimal"
          aria-label="Montant minimum"
          placeholder="Montant min (€)"
          value={filters.min}
          onChange={(e) => setFilter("min", e.target.value)}
        />
        <div className="flex gap-2">
          <Input
            type="number"
            inputMode="decimal"
            aria-label="Montant maximum"
            placeholder="Montant max (€)"
            value={filters.max}
            onChange={(e) => setFilter("max", e.target.value)}
          />
          {hasFilters && (
            <Button
              variant="ghost"
              size="icon"
              aria-label="Effacer les filtres"
              onClick={() => {
                setFilters(EMPTY);
                setPage(1);
              }}
            >
              <X />
            </Button>
          )}
        </div>
      </div>

      <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            className="size-4 accent-primary"
            checked={filters.review}
            onChange={(e) => setFilter("review", e.target.checked)}
          />
          À vérifier seulement{" "}
          <span className="text-muted-foreground">(proposées par l&apos;IA, pas encore validées)</span>
        </label>
        {filters.review && data && data.total > 0 && (
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

      {error ? (
        <ErrorMessage error={error} />
      ) : isPending ? (
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
          <div className={cn("rounded-xl border transition-opacity", isFetching && "opacity-60")}>
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
        className={cn(
          "inline-flex max-w-40 items-center gap-1 truncate rounded-md border px-2 py-0.5 text-xs transition-colors hover:bg-muted",
          !tx.category && "border-dashed text-muted-foreground",
          tx.category === "Inconnu" && "border-amber-500/40 bg-amber-500/10 text-amber-700 dark:text-amber-300",
          (tx.category_source === "user" || tx.category_source === "rule" || validated) &&
            "border-foreground/30 font-medium",
        )}
      >
        {tx.category ?? "À classer"}
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

"use client";

import { useMutation } from "@tanstack/react-query";
import { FileStack, RefreshCw, Search, Trash2 } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { toast } from "sonner";

import { BankBadge, CheckBadge, EmptyState, ErrorMessage, PageHeader } from "@/components/common";
import { MultiSelect, type MultiOption } from "@/components/multi-select";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api, unwrap, type StatementFile } from "@/lib/api";
import { BANK_LABELS, formatBytes, formatDate } from "@/lib/format";
import { cn } from "@/lib/utils";
import { useFiles, useInvalidateData } from "@/lib/queries";

const STATUS: Record<string, { label: string; variant: "secondary" | "destructive" | "outline" }> = {
  parsed: { label: "Importé", variant: "secondary" },
  failed: { label: "Erreur", variant: "destructive" },
  unsupported: { label: "Non pris en charge", variant: "outline" },
};

export function FilesView() {
  const { data, error, isPending } = useFiles();
  const invalidate = useInvalidateData();
  const [toDelete, setToDelete] = useState<StatementFile | null>(null);
  // Multiple-choice filters: null = everything, [] = nothing.
  const [statuses, setStatuses] = useState<string[] | null>(null);
  const [banks, setBanks] = useState<string[] | null>(null);
  const [q, setQ] = useState("");
  const shown = (data ?? []).filter(
    (f) =>
      (statuses === null || statuses.includes(f.status)) &&
      (banks === null || banks.includes(f.bank_code ?? NO_BANK)) &&
      (!q.trim() || f.filename.toLowerCase().includes(q.trim().toLowerCase())),
  );
  const bankOptions: MultiOption[] = [...new Set((data ?? []).map((f) => f.bank_code ?? NO_BANK))].map((code) => ({
    value: code,
    label: code === NO_BANK ? "Banque non reconnue" : (BANK_LABELS[code] ?? code),
  }));
  const filtered = statuses !== null || banks !== null || q.trim() !== "";

  const reparse = useMutation({
    mutationFn: (id: number) =>
      unwrap(api.POST("/api/files/{file_id}/reparse", { params: { path: { file_id: id } } })),
    onSuccess: async (r) => {
      await invalidate();
      if (r.status === "imported") toast.success(`${r.filename} réanalysé : ${r.inserted} opérations`);
      else toast.error(`${r.filename} : ${r.error ?? r.status}`);
    },
    onError: (e) => toast.error(e.message),
  });

  const reparseAll = useMutation({
    mutationFn: () => unwrap(api.POST("/api/files/reparse-all")),
    onSuccess: async (results) => {
      await invalidate();
      const ok = results.filter((r) => r.status === "imported").length;
      toast.success(`${ok}/${results.length} fichiers réanalysés`);
    },
    onError: (e) => toast.error(e.message),
  });

  const remove = useMutation({
    mutationFn: (id: number) => unwrap(api.DELETE("/api/files/{file_id}", { params: { path: { file_id: id } } })),
    onSuccess: async () => {
      await invalidate();
      toast.success("Fichier supprimé avec ses opérations");
      setToDelete(null);
    },
    onError: (e) => toast.error(e.message),
  });

  return (
    <>
      <PageHeader
        title="Fichiers importés"
        description="Historique des relevés. Supprimer un fichier retire les opérations qu'il est le seul à contenir."
        actions={
          data?.length ? (
            <Button variant="outline" size="sm" disabled={reparseAll.isPending} onClick={() => reparseAll.mutate()}>
              <RefreshCw className={reparseAll.isPending ? "animate-spin" : undefined} /> Tout réanalyser
            </Button>
          ) : null
        }
      />

      {data && data.length > 0 && (
        <>
          <FilesSummary files={data} statuses={statuses} onStatuses={setStatuses} />
          <div className="mb-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
            <div className="relative sm:col-span-2">
              <Search className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                aria-label="Rechercher un fichier"
                placeholder="Rechercher un nom de fichier"
                value={q}
                onChange={(e) => setQ(e.target.value)}
                className="pl-8"
              />
            </div>
            <MultiSelect
              label="statuts"
              allLabel="Tous les statuts"
              options={STATUS_OPTIONS}
              value={statuses}
              onChange={setStatuses}
            />
            <MultiSelect label="banques" allLabel="Toutes les banques" options={bankOptions} value={banks} onChange={setBanks} />
          </div>
          {filtered && (
            <p className="mb-3 text-sm text-muted-foreground">
              {shown.length} fichier{shown.length > 1 ? "s" : ""} sur {data.length} ·{" "}
              <button
                type="button"
                className="underline underline-offset-4"
                onClick={() => {
                  setStatuses(null);
                  setBanks(null);
                  setQ("");
                }}
              >
                tout afficher
              </button>
            </p>
          )}
        </>
      )}

      {error ? (
        <ErrorMessage error={error} />
      ) : isPending ? (
        <Skeleton className="h-72 w-full" />
      ) : data.length === 0 ? (
        <EmptyState icon={FileStack} title="Aucun fichier importé">
          <Link href="/import" className="underline underline-offset-4">
            Importer des relevés
          </Link>
        </EmptyState>
      ) : (
        <div className="rounded-xl border bg-card shadow-xs">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Fichier</TableHead>
                <TableHead className="hidden sm:table-cell">Relevé du</TableHead>
                <TableHead className="text-right">Opérations</TableHead>
                <TableHead className="hidden md:table-cell">Contrôle</TableHead>
                <TableHead className="w-20" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {shown.map((f) => (
                <TableRow key={f.id}>
                  <TableCell className="max-w-0 w-full">
                    <p className="truncate font-medium" title={f.filename}>
                      {f.filename}
                    </p>
                    <div className="mt-1 flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
                      <BankBadge code={f.bank_code} />
                      {f.status !== "parsed" && <Badge variant={STATUS[f.status]?.variant}>{STATUS[f.status]?.label}</Badge>}
                      <span>{formatBytes(f.size)}</span>
                    </div>
                    {f.error && <p className="mt-1 truncate text-xs text-destructive" title={f.error}>{f.error}</p>}
                  </TableCell>
                  <TableCell className="hidden whitespace-nowrap sm:table-cell">{formatDate(f.statement_date)}</TableCell>
                  <TableCell className="text-right font-mono tabular-nums">{f.transaction_count}</TableCell>
                  <TableCell className="hidden md:table-cell">
                    {f.status === "parsed" && <CheckBadge ok={f.check_ok} />}
                  </TableCell>
                  <TableCell>
                    <div className="flex justify-end gap-1">
                      <Button
                        variant="ghost"
                        size="icon-sm"
                        aria-label={`Réanalyser ${f.filename}`}
                        title="Réanalyser"
                        disabled={reparse.isPending && reparse.variables === f.id}
                        onClick={() => reparse.mutate(f.id)}
                      >
                        <RefreshCw className={reparse.isPending && reparse.variables === f.id ? "animate-spin" : undefined} />
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon-sm"
                        aria-label={`Supprimer ${f.filename}`}
                        title="Supprimer"
                        onClick={() => setToDelete(f)}
                      >
                        <Trash2 />
                      </Button>
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}

      <Dialog open={toDelete !== null} onOpenChange={(open) => !open && setToDelete(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Supprimer ce fichier ?</DialogTitle>
            <DialogDescription>
              « {toDelete?.filename} » et ses {toDelete?.transaction_count} opérations seront retirés. Les opérations
              également présentes dans un autre relevé sont conservées.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <DialogClose render={<Button variant="outline" />}>Annuler</DialogClose>
            <Button variant="destructive" disabled={remove.isPending} onClick={() => toDelete && remove.mutate(toDelete.id)}>
              Supprimer
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}

const NO_BANK = "__none__";
const STATUS_OPTIONS: MultiOption[] = [
  { value: "parsed", label: "Relevés lus" },
  { value: "unsupported", label: "Non pris en charge" },
  { value: "failed", label: "En erreur" },
];

const STATUS_TILES = [
  { key: null, label: "Fichiers importés", hint: "Tous les PDF déposés" },
  { key: "parsed", label: "Relevés lus", hint: "Opérations extraites" },
  { key: "unsupported", label: "Non pris en charge", hint: "Format pas encore lu" },
  { key: "failed", label: "En erreur", hint: "Lecture impossible" },
] as const;

/** Key figures; a tile is a shortcut that shows only its status (click again to show everything). */
function FilesSummary({
  files,
  statuses,
  onStatuses,
}: {
  files: StatementFile[];
  statuses: string[] | null;
  onStatuses: (statuses: string[] | null) => void;
}) {
  const count = (status: string | null) => (status ? files.filter((f) => f.status === status).length : files.length);
  const byBank = Object.entries(
    files
      .filter((f) => f.status === "parsed" && f.bank_code)
      .reduce<Record<string, number>>((acc, f) => ({ ...acc, [f.bank_code!]: (acc[f.bank_code!] ?? 0) + 1 }), {}),
  ).sort((a, b) => b[1] - a[1]);
  const unsupported = count("unsupported");

  return (
    <div className="mb-6 space-y-3">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {STATUS_TILES.map((t) => {
          const n = count(t.key);
          const active = t.key === null ? statuses === null : statuses?.length === 1 && statuses[0] === t.key;
          return (
            <button
              key={t.label}
              type="button"
              aria-pressed={active}
              disabled={t.key !== null && n === 0}
              onClick={() => onStatuses(active || t.key === null ? null : [t.key])}
              className={cn(
                "rounded-xl border bg-card p-3 text-left transition-colors hover:bg-muted/50 disabled:cursor-default disabled:opacity-60 disabled:hover:bg-card",
                active && "border-foreground/40 bg-muted",
              )}
            >
              <p className="text-sm text-muted-foreground">{t.label}</p>
              <p className="mt-0.5 text-2xl font-semibold tabular-nums">{n}</p>
              <p className="text-xs text-muted-foreground">{t.hint}</p>
            </button>
          );
        })}
      </div>
      <div className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
        <span>Relevés lus par banque :</span>
        {byBank.length === 0 && <span>aucun</span>}
        {byBank.map(([bank, n]) => (
          <span key={bank} className="flex items-center gap-1">
            <BankBadge code={bank} /> <span className="tabular-nums">{n}</span>
          </span>
        ))}
      </div>
      {unsupported > 0 && (
        <p className="text-sm text-muted-foreground">
          {unsupported} fichier{unsupported > 1 ? "s" : ""} non pris en charge : ce sont des documents conservés mais
          dont les opérations ne sont pas encore lues (par exemple les relevés Boursorama « espèces », « titres » ou
          « coupons »). Ils ne comptent pas dans les relevés lus.
        </p>
      )}
    </div>
  );
}

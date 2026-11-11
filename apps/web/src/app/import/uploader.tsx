"use client";

import {
  CheckCircle2,
  CircleSlash,
  Copy,
  FileUp,
  Loader2,
  XCircle,
} from "lucide-react";
import Link from "next/link";
import { useRef, useState } from "react";

import { BankBadge, CheckBadge } from "@/components/common";
import { Button } from "@/components/ui/button";
import type { ImportResult } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { useInvalidateData } from "@/lib/queries";
import { cn } from "@/lib/utils";

type Item = { id: string; file: File; state: "pending" | "uploading" | "done" | "error"; result?: ImportResult };

const BANK_CODES: Record<string, string> = { "Crédit Agricole": "CA", "Crédit Mutuel": "CM", Boursorama: "BOURSO" };

async function uploadOne(file: File): Promise<ImportResult> {
  const body = new FormData();
  body.append("files", file);
  const response = await fetch("/api/uploads", { method: "POST", body });
  if (!response.ok) throw new Error(`Erreur ${response.status}`);
  const [result] = (await response.json()) as ImportResult[];
  return result;
}

export function Uploader() {
  const [items, setItems] = useState<Item[]>([]);
  const [dragging, setDragging] = useState(false);
  const [busy, setBusy] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const invalidate = useInvalidateData();

  const update = (id: string, patch: Partial<Item>) =>
    setItems((prev) => prev.map((it) => (it.id === id ? { ...it, ...patch } : it)));

  async function addFiles(fileList: FileList | null) {
    const files = Array.from(fileList ?? []).filter((f) => f.name.toLowerCase().endsWith(".pdf"));
    if (!files.length) return;
    const batch: Item[] = files.map((file) => ({ id: crypto.randomUUID(), file, state: "pending" }));
    setItems((prev) => [...batch, ...prev]);
    setBusy(true);
    // One file per request: per-file progress, and one bad file never blocks the others.
    for (const item of batch) {
      update(item.id, { state: "uploading" });
      try {
        update(item.id, { state: "done", result: await uploadOne(item.file) });
      } catch (error) {
        update(item.id, {
          state: "error",
          result: {
            filename: item.file.name,
            status: "failed",
            error: error instanceof Error ? error.message : "Erreur réseau",
          } as ImportResult,
        });
      }
    }
    setBusy(false);
    await invalidate();
  }

  const done = items.filter((i) => i.result);
  const inserted = done.reduce((n, i) => n + (i.result?.inserted ?? 0), 0);
  const duplicates = done.reduce((n, i) => n + (i.result?.duplicates ?? 0), 0);

  return (
    <div className="space-y-6">
      <div
        role="button"
        tabIndex={0}
        aria-label="Déposer des relevés PDF ou cliquer pour choisir des fichiers"
        onClick={() => inputRef.current?.click()}
        onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && inputRef.current?.click()}
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          void addFiles(e.dataTransfer.files);
        }}
        className={cn(
          "flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed px-6 py-16 text-center transition-colors outline-none hover:bg-muted/50 focus-visible:ring-3 focus-visible:ring-ring/50",
          dragging && "border-primary bg-muted",
        )}
      >
        <FileUp className="mb-3 size-10 text-muted-foreground" />
        <p className="font-medium">Glissez vos relevés PDF ici</p>
        <p className="mt-1 text-sm text-muted-foreground">ou cliquez pour les sélectionner (plusieurs fichiers possibles)</p>
        <input
          ref={inputRef}
          type="file"
          accept="application/pdf,.pdf"
          multiple
          hidden
          onChange={(e) => {
            void addFiles(e.target.files);
            e.target.value = "";
          }}
        />
      </div>

      {items.length > 0 && (
        <div className="space-y-3">
          <div className="flex flex-wrap items-center justify-between gap-2 text-sm">
            <p className="text-muted-foreground">
              {done.length}/{items.length} fichier{items.length > 1 ? "s" : ""} traité{done.length > 1 ? "s" : ""} ·{" "}
              <span className="font-medium text-foreground">{inserted} nouvelle{inserted > 1 ? "s" : ""} opération{inserted > 1 ? "s" : ""}</span>
              {duplicates > 0 && ` · ${duplicates} doublon${duplicates > 1 ? "s" : ""} ignoré${duplicates > 1 ? "s" : ""}`}
            </p>
            {!busy && inserted > 0 && (
              <Button variant="outline" size="sm" render={<Link href="/operations" />}>
                Voir les opérations
              </Button>
            )}
          </div>
          <ul className="space-y-2">
            {items.map((item) => (
              <ResultRow key={item.id} name={item.file.name} state={item.state} result={item.result} />
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

export function ResultRow({ name, state, result }: { name: string; state: Item["state"]; result?: ImportResult }) {
  const r = result;
  const status = state === "done" || state === "error" ? r?.status : state;

  const icon = {
    pending: <Loader2 className="size-5 text-muted-foreground" />,
    uploading: <Loader2 className="size-5 animate-spin text-muted-foreground" />,
    imported: <CheckCircle2 className="size-5 text-positive" />,
    already_imported: <Copy className="size-5 text-muted-foreground" />,
    unsupported: <CircleSlash className="size-5 text-amber-500" />,
    rejected: <CircleSlash className="size-5 text-amber-500" />,
    failed: <XCircle className="size-5 text-negative" />,
  }[status ?? "pending"];

  let detail: React.ReactNode = status === "uploading" ? "Analyse en cours…" : "En attente";
  if (r) {
    if (r.status === "imported")
      detail = (
        <>
          <span className="font-medium text-foreground">+{r.inserted} opération{r.inserted > 1 ? "s" : ""}</span>
          {r.duplicates > 0 && ` · ${r.duplicates} déjà connue${r.duplicates > 1 ? "s" : ""}`}
          {r.accounts.length > 0 && ` · ${r.accounts.join(", ")}`}
        </>
      );
    else if (r.status === "already_imported") detail = "Ce fichier a déjà été importé.";
    else detail = r.error ?? "Erreur";
  }

  return (
    <li className="flex items-start gap-3 rounded-lg border bg-card p-3">
      <div className="mt-0.5">{icon}</div>
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <span className="truncate text-sm font-medium" title={name}>
            {name}
          </span>
          {r?.bank && <BankBadge code={BANK_CODES[r.bank]} />}
          {r?.statement_date && <span className="text-xs text-muted-foreground">relevé du {formatDate(r.statement_date)}</span>}
        </div>
        <p className="mt-0.5 text-sm text-muted-foreground">{detail}</p>
      </div>
      {r?.status === "imported" && <CheckBadge ok={r.check_ok} />}
    </li>
  );
}

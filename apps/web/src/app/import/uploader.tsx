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
import { NativeSelect } from "@/components/native-select";
import { NewUserDialog } from "@/components/space-switcher";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import type { ImportResult } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { useInvalidateData } from "@/lib/queries";
import { useSpace } from "@/lib/space";
import { cn } from "@/lib/utils";

type Item = {
  id: string;
  file: File;
  spaceId?: number; // user chosen for this file (undefined: the holder read on the statement decides)
  state: "pending" | "uploading" | "done" | "error";
  result?: ImportResult;
};

const BANK_CODES: Record<string, string> = { "Crédit Agricole": "CA", "Crédit Mutuel": "CM", Boursorama: "BOURSO", LCL: "LCL" };

const AUTO = "auto";
const NEW = "new";

async function uploadOne(file: File, spaceId?: number, fallbackSpaceId?: number): Promise<ImportResult> {
  const body = new FormData();
  body.append("files", file);
  if (spaceId !== undefined) body.append("space_id", String(spaceId));
  // Files whose holder cannot be known (unreadable, unsupported) go to the user shown in the app.
  if (fallbackSpaceId !== undefined) body.append("fallback_space_id", String(fallbackSpaceId));
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
  const { spaces, spaceId: shownSpaceId, setSpaceId } = useSpace();
  // Who the statements belong to: chosen here, or read on each statement ("auto").
  const [target, setTarget] = useState<string>(AUTO);
  const [adding, setAdding] = useState(false);
  const targetId = target === AUTO || !spaces.some((s) => String(s.id) === target) ? undefined : Number(target);

  const update = (id: string, patch: Partial<Item>) =>
    setItems((prev) => prev.map((it) => (it.id === id ? { ...it, ...patch } : it)));

  async function addFiles(fileList: FileList | null) {
    const files = Array.from(fileList ?? []).filter((f) => f.name.toLowerCase().endsWith(".pdf"));
    if (!files.length) return;
    const batch: Item[] = files.map((file) => ({
      id: crypto.randomUUID(),
      file,
      spaceId: targetId,
      state: "pending",
    }));
    setItems((prev) => [...batch, ...prev]);
    setBusy(true);
    // One file per request: per-file progress, and one bad file never blocks the others.
    for (const item of batch) {
      update(item.id, { state: "uploading" });
      try {
        update(item.id, { state: "done", result: await uploadOne(item.file, item.spaceId, shownSpaceId) });
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
  // Statements of another holder were imported: say where they went (each holder has a space).
  const created = done.map((i) => i.result!).filter((r) => r.space_created && r.space_id != null);
  const showSpaces = spaces.length > 1 || created.length > 0;

  const targetName = spaces.find((s) => s.id === targetId)?.name;

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 rounded-xl border bg-card p-4 sm:flex-row sm:items-end sm:justify-between">
        <div className="grid gap-1.5 sm:w-80">
          <Label htmlFor="import-target">Importer pour</Label>
          <NativeSelect
            id="import-target"
            value={targetId === undefined ? AUTO : String(targetId)}
            disabled={busy}
            onChange={(e) => (e.target.value === NEW ? setAdding(true) : setTarget(e.target.value))}
          >
            <option value={AUTO}>Détection automatique (nom lu sur le relevé)</option>
            {spaces.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
            <option value={NEW}>＋ Nouvel utilisateur…</option>
          </NativeSelect>
        </div>
        <p className="text-sm text-muted-foreground sm:max-w-sm sm:text-right">
          {targetName
            ? `Les relevés déposés iront chez ${targetName}, quel que soit le nom écrit dessus.`
            : "Chaque relevé va chez la personne dont le nom est écrit dessus ; un nouveau nom crée un nouvel utilisateur."}
        </p>
      </div>
      {adding && (
        <NewUserDialog
          onClose={() => setAdding(false)}
          onCreated={(space) => {
            setTarget(String(space.id));
            setSpaceId(space.id);
          }}
        />
      )}

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
        <p className="font-medium">
          Glissez {targetName ? `les relevés de ${targetName}` : "vos relevés PDF"} ici
        </p>
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
              <Button variant="outline" size="sm" nativeButton={false} render={<Link href="/operations" />}>
                Voir les opérations
              </Button>
            )}
          </div>
          {!busy && created.length > 0 && (
            <div className="rounded-lg border border-primary/30 bg-primary/5 p-3 text-sm" role="status">
              {created.length === 1 ? "Nouveau titulaire détecté" : "Nouveaux titulaires détectés"} : un utilisateur a été
              créé pour{" "}
              {created.map((r, i) => (
                <span key={r.space_id}>
                  {i > 0 && ", "}
                  <button
                    type="button"
                    className="font-medium underline underline-offset-4"
                    onClick={() => setSpaceId(r.space_id!)}
                  >
                    {r.space_name}
                  </button>
                </span>
              ))}
              . Passez de l&apos;un à l&apos;autre avec le sélecteur du menu.
            </div>
          )}
          <ul className="space-y-2">
            {items.map((item) => (
              <ResultRow
                key={item.id}
                name={item.file.name}
                state={item.state}
                result={item.result}
                showSpace={showSpaces}
              />
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

export function ResultRow({
  name,
  state,
  result,
  showSpace = false,
}: {
  name: string;
  state: Item["state"];
  result?: ImportResult;
  showSpace?: boolean;
}) {
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
          {showSpace && r?.space_name && (
            <Badge variant="outline" title="Utilisateur auquel ce relevé a été rattaché">
              {r.space_name}
              {r.space_created && " · nouvel utilisateur"}
            </Badge>
          )}
        </div>
        <p className="mt-0.5 text-sm text-muted-foreground">{detail}</p>
        {r?.warnings?.map((w) => (
          <p key={w} className="mt-0.5 text-xs text-amber-700 dark:text-amber-400">
            {w}
          </p>
        ))}
      </div>
      {r?.status === "imported" && <CheckBadge ok={r.check_ok} />}
    </li>
  );
}

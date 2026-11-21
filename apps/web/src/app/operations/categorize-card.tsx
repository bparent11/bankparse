"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, Loader2, Sparkles, XCircle } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { NativeSelect } from "@/components/native-select";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api, unwrap, type Schemas } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { useCategorizeStatus, useInvalidateData, useLatestCategorizeJob } from "@/lib/queries";
import { useSpace } from "@/lib/space";

type Mode = "new" | "all";
type Status = Schemas["CategorizeStatus"];

export function CategorizeCard() {
  const status = useCategorizeStatus();
  const job = useLatestCategorizeJob();
  const client = useQueryClient();
  const invalidate = useInvalidateData();
  const [open, setOpen] = useState(false);
  const running = job.data?.status === "running";

  // Refresh the table while the job runs (every ~10 s) and once when it ends.
  const previous = useRef<string | undefined>(undefined);
  const lastRefresh = useRef(0);
  useEffect(() => {
    const s = job.data?.status;
    if (previous.current === "running" && s !== "running") void invalidate();
    else if (s === "running" && job.dataUpdatedAt - lastRefresh.current > 10_000) {
      lastRefresh.current = job.dataUpdatedAt;
      void client.invalidateQueries({ queryKey: ["transactions"] });
    }
    previous.current = s;
  }, [job.data?.status, job.dataUpdatedAt, invalidate, client]);

  const cancel = useMutation({
    mutationFn: (id: number) =>
      unwrap(api.POST("/api/categorize/jobs/{job_id}/cancel", { params: { path: { job_id: id } } })),
    onError: (e) => toast.error(e.message),
  });

  if (status.isPending || status.error) return null;
  const s = status.data;
  const ready = s.ollama_ok && s.models.length > 0;
  const j = job.data;
  const percent = j && j.total > 0 ? Math.round((100 * j.done) / j.total) : 0;

  return (
    <section className="mb-4 rounded-xl border bg-card p-4" aria-labelledby="categorize-title">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 id="categorize-title" className="flex items-center gap-2 font-medium">
            <Sparkles className="size-4" /> Catégoriser avec l&apos;IA locale
          </h2>
          <p className="mt-0.5 text-sm text-muted-foreground">
            {ready ? (
              <>
                {s.uncategorized} opération{s.uncategorized > 1 ? "s" : ""} sans catégorie
                {s.unknown > 0 && ` · ${s.unknown} « Inconnu »`}
                {s.to_review > 0 && ` · ${s.to_review} à vérifier`} · sur votre PC, rien n&apos;est envoyé en ligne
              </>
            ) : (
              <span className="text-amber-700 dark:text-amber-400">{s.reason}</span>
            )}
          </p>
        </div>
        {running ? (
          <Button variant="outline" size="sm" disabled={cancel.isPending} onClick={() => j && cancel.mutate(j.id)}>
            Annuler
          </Button>
        ) : (
          <Button size="sm" disabled={!ready} onClick={() => setOpen(true)}>
            <Sparkles /> Catégoriser…
          </Button>
        )}
      </div>

      {j && (running || j.finished_at) && (
        <div className="mt-3 space-y-2 border-t pt-3 text-sm" aria-live="polite">
          {running && (
            <div
              className="h-2 overflow-hidden rounded-full bg-muted"
              role="progressbar"
              aria-valuenow={percent}
              aria-valuemin={0}
              aria-valuemax={100}
              aria-label="Progression de la catégorisation"
            >
              <div className="h-full rounded-full bg-primary transition-all" style={{ width: `${percent}%` }} />
            </div>
          )}
          <p className="flex items-center gap-2">
            {running && <Loader2 className="size-4 animate-spin text-muted-foreground" />}
            {j.status === "done" && <CheckCircle2 className="size-4 text-positive" />}
            {(j.status === "failed" || j.status === "cancelled") && <XCircle className="size-4 text-negative" />}
            <span className="text-muted-foreground">
              {running && `${j.done}/${j.total} · `}
              {j.message}
            </span>
          </p>
          {running && (
            <p className="text-xs text-muted-foreground">
              Modèle {j.model} · {(j.batch_size ?? 1) > 1 ? "rapide" : "précis"}
              {(j.date_from || j.date_to) && ` · période ${formatDate(j.date_from)} → ${formatDate(j.date_to)}`}. Vous
              pouvez continuer à utiliser l&apos;appli pendant ce temps.
            </p>
          )}
        </div>
      )}

      {open && <LaunchDialog status={s} onClose={() => setOpen(false)} />}
    </section>
  );
}

function LaunchDialog({ status, onClose }: { status: Status; onClose: () => void }) {
  const client = useQueryClient();
  const { spaceId } = useSpace();
  const [mode, setMode] = useState<Mode>("new");
  const [batchSize, setBatchSize] = useState(status.default_batch_size);
  // Fast runs use a smaller model, precise runs a bigger one; the user can still pick any installed model.
  const suggested = (size: number) => (size > 1 ? status.fast_model : status.default_model) ?? status.models[0]?.name ?? "";
  const [model, setModel] = useState(() => suggested(status.default_batch_size));
  const chooseSpeed = (size: number) => {
    setBatchSize(size);
    setModel(suggested(size));
  };
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");

  const count = useQuery({
    queryKey: ["categorize", "count", spaceId, mode, dateFrom, dateTo],
    queryFn: () =>
      unwrap(
        api.GET("/api/categorize/count", {
          params: {
            query: { space_id: spaceId, mode, date_from: dateFrom || undefined, date_to: dateTo || undefined },
          },
        }),
      ),
  });

  const start = useMutation({
    mutationFn: () =>
      unwrap(
        api.POST("/api/categorize", {
          body: {
            model,
            mode,
            date_from: dateFrom || null,
            date_to: dateTo || null,
            batch_size: batchSize,
            space_id: spaceId ?? null,
          },
        }),
      ),
    onSuccess: (started) => {
      client.setQueryData(["categorize", "latest", spaceId], started);
      onClose();
    },
    onError: (e) => toast.error(e.message),
  });

  const n = count.data?.count;

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="sm:max-w-lg">
        <form
          className="grid gap-4"
          onSubmit={(e) => {
            e.preventDefault();
            if (model && n) start.mutate();
          }}
        >
          <DialogHeader>
            <DialogTitle>Lancer une catégorisation</DialogTitle>
            <DialogDescription>
              Chaque opération est analysée seule par le modèle choisi, avec son compte, sa date et son montant. Vos
              propres choix ne sont jamais modifiés et servent d&apos;exemples.
            </DialogDescription>
          </DialogHeader>

          <fieldset className="grid gap-2 text-sm">
            <legend className="mb-1 text-sm font-medium">Vitesse</legend>
            <label className="flex items-start gap-2">
              <input
                type="radio"
                name="speed"
                className="mt-0.5 accent-primary"
                checked={batchSize > 1}
                onChange={() => chooseSpeed(10)}
              />
              <span>
                Rapide — petit modèle, 10 opérations par requête
                <span className="block text-xs text-muted-foreground">
                  Le plus rapide, un peu moins précis. Idéal pour un premier passage.
                </span>
              </span>
            </label>
            <label className="flex items-start gap-2">
              <input
                type="radio"
                name="speed"
                className="mt-0.5 accent-primary"
                checked={batchSize === 1}
                onChange={() => chooseSpeed(1)}
              />
              <span>
                Précis — gros modèle, une opération à la fois
                <span className="block text-xs text-muted-foreground">
                  Le plus fiable, pour affiner ensuite (plus lent).
                </span>
              </span>
            </label>
          </fieldset>

          <div className="grid gap-1.5">
            <Label htmlFor="categorize-model">Modèle</Label>
            <NativeSelect id="categorize-model" value={model} onChange={(e) => setModel(e.target.value)}>
              {status.models.map((m) => (
                <option key={m.name} value={m.name}>
                  {m.name} ({m.size_gb} Go)
                  {m.name === status.fast_model ? " — suggéré en rapide" : ""}
                  {m.name === status.default_model ? " — suggéré en précis" : ""}
                </option>
              ))}
            </NativeSelect>
            <p className="text-xs text-muted-foreground">Plus le modèle est gros, plus il est précis… et lent.</p>
            {status.missing_models.length > 0 && (
              <p className="text-xs text-amber-700 dark:text-amber-400">
                Non installé{status.missing_models.length > 1 ? "s" : ""} :{" "}
                {status.missing_models.map((m) => (
                  <code key={m} className="mr-1 rounded bg-muted px-1">
                    ollama pull {m}
                  </code>
                ))}
                — un autre modèle installé est proposé à la place.
              </p>
            )}
          </div>

          <fieldset className="grid gap-2 text-sm">
            <legend className="mb-1 text-sm font-medium">Opérations</legend>
            <label className="flex items-center gap-2">
              <input
                type="radio"
                name="mode"
                className="accent-primary"
                checked={mode === "new"}
                onChange={() => setMode("new")}
              />
              Jamais catégorisées
            </label>
            <label className="flex items-center gap-2">
              <input
                type="radio"
                name="mode"
                className="accent-primary"
                checked={mode === "all"}
                onChange={() => setMode("all")}
              />
              Toutes, sauf celles que vous avez classées vous-même
            </label>
          </fieldset>

          <div className="grid gap-1.5">
            <span className="text-sm font-medium">Période (facultatif)</span>
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              du
              <Input type="date" aria-label="Date de début" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} />
              au
              <Input type="date" aria-label="Date de fin" value={dateTo} onChange={(e) => setDateTo(e.target.value)} />
            </div>
          </div>

          <DialogFooter className="items-center sm:justify-between">
            <span className="text-sm text-muted-foreground">
              {n === undefined ? "…" : `${n} opération${n > 1 ? "s" : ""} à analyser`}
            </span>
            <Button type="submit" disabled={!model || !n || start.isPending}>
              <Sparkles /> Lancer
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

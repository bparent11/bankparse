"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { toast } from "sonner";

import { Amount } from "@/components/common";
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
import { Label } from "@/components/ui/label";
import { api, unwrap, type Transaction } from "@/lib/api";
import { formatShortDate } from "@/lib/format";
import { useCategories, useInvalidateData } from "@/lib/queries";

export function CategoryDialog({ tx, onClose }: { tx: Transaction | null; onClose: () => void }) {
  const categories = useCategories();
  const invalidate = useInvalidateData();
  const [category, setCategory] = useState("");
  const [reason, setReason] = useState("");
  const [applyToSimilar, setApplyToSimilar] = useState(false);
  const [editedId, setEditedId] = useState<number | null>(null);
  if (tx && editedId !== tx.id) {
    // A different operation was opened: reset the form (no effect needed).
    setEditedId(tx.id);
    setCategory(tx.category ?? "");
    setReason("");
    setApplyToSimilar(false);
  }

  const similar = useQuery({
    queryKey: ["similar", tx?.id],
    enabled: tx !== null,
    queryFn: () =>
      unwrap(api.GET("/api/transactions/{transaction_id}/similar", { params: { path: { transaction_id: tx!.id } } })),
  });

  const save = useMutation({
    mutationFn: () =>
      unwrap(
        api.PATCH("/api/transactions/{transaction_id}/category", {
          params: { path: { transaction_id: tx!.id } },
          body: { category, reason: reason.trim() || null, apply_to_similar: applyToSimilar && hasSimilar },
        }),
      ),
    onSuccess: async (r) => {
      await invalidate();
      toast.success(
        r.updated > 1 ? `${r.updated} opérations classées en « ${category} »` : `Opération classée en « ${category} »`,
      );
      close();
    },
    onError: (e) => toast.error(e.message),
  });

  const close = () => {
    setEditedId(null);
    onClose();
  };
  const hasSimilar = (similar.data?.count ?? 0) > 0;

  return (
    <Dialog open={tx !== null} onOpenChange={(open) => !open && close()}>
      <DialogContent className="sm:max-w-lg">
        <form
          className="grid gap-4"
          onSubmit={(e) => {
            e.preventDefault();
            if (category) save.mutate();
          }}
        >
          <DialogHeader>
            <DialogTitle>Catégorie de l&apos;opération</DialogTitle>
            <DialogDescription className="break-words">
              « {tx?.label} »
              {tx && (
                <>
                  {" "}
                  · {formatShortDate(tx.operation_date)} · <Amount value={tx.amount} />
                </>
              )}
            </DialogDescription>
          </DialogHeader>

          <div className="grid gap-1.5">
            <Label htmlFor="category-select">Catégorie</Label>
            <NativeSelect id="category-select" value={category} onChange={(e) => setCategory(e.target.value)}>
              <option value="" disabled>
                Choisir une catégorie…
              </option>
              {categories.data?.map((c) => (
                <option key={c.id} value={c.name}>
                  {c.name}
                </option>
              ))}
            </NativeSelect>
          </div>

          <div className="grid gap-1.5">
            <Label htmlFor="category-reason">
              Pourquoi ? <span className="font-normal text-muted-foreground">(facultatif)</span>
            </Label>
            <textarea
              id="category-reason"
              value={reason}
              maxLength={300}
              rows={2}
              onChange={(e) => setReason(e.target.value)}
              placeholder="Ex : Emma me rembourse sa part du loyer chaque mois"
              className="w-full resize-y rounded-lg border border-input bg-transparent px-2.5 py-1.5 text-sm outline-none placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 dark:bg-input/30"
            />
            <p className="text-xs text-muted-foreground">
              Votre explication est donnée à l&apos;IA (sur votre PC) pour classer les opérations comparables lors des
              prochaines catégorisations.
            </p>
          </div>

          {hasSimilar && (
            <label className="flex items-start gap-2 text-sm">
              <input
                type="checkbox"
                className="mt-0.5 size-4 accent-primary"
                checked={applyToSimilar}
                onChange={(e) => setApplyToSimilar(e.target.checked)}
              />
              <span>
                Appliquer aussi aux {similar.data!.count} autre{similar.data!.count > 1 ? "s" : ""} opération
                {similar.data!.count > 1 ? "s" : ""} au libellé similaire
                <span className="mt-0.5 block text-xs text-muted-foreground">
                  ex : {similar.data!.examples.map((l) => `« ${l} »`).join(", ")}
                </span>
              </span>
            </label>
          )}

          <DialogFooter>
            <Button type="submit" disabled={!category || save.isPending}>
              Enregistrer
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

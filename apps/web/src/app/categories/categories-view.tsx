"use client";

import { useMutation } from "@tanstack/react-query";
import { Lock, Pencil, Plus, Trash2 } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { toast } from "sonner";

import { ErrorMessage, PageHeader } from "@/components/common";
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
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { api, unwrap, type Schemas } from "@/lib/api";
import { useCategories, useInvalidateData } from "@/lib/queries";

type Category = Schemas["CategoryOut"];

export function CategoriesView() {
  const { data, error, isPending } = useCategories();
  const invalidate = useInvalidateData();
  const [newName, setNewName] = useState("");
  const [renaming, setRenaming] = useState<Category | null>(null);
  const [deleting, setDeleting] = useState<Category | null>(null);

  const create = useMutation({
    mutationFn: (name: string) => unwrap(api.POST("/api/categories", { body: { name } })),
    onSuccess: async (c) => {
      await invalidate();
      setNewName("");
      toast.success(`Catégorie « ${c.name} » ajoutée`);
    },
    onError: (e) => toast.error(e.message),
  });
  const remove = useMutation({
    mutationFn: (id: number) =>
      unwrap(api.DELETE("/api/categories/{category_id}", { params: { path: { category_id: id } } })),
    onSuccess: async () => {
      await invalidate();
      toast.success("Catégorie supprimée");
      setDeleting(null);
    },
    onError: (e) => toast.error(e.message),
  });

  return (
    <>
      <PageHeader
        title="Catégories"
        description="La liste utilisée pour classer vos opérations, par vous et par l'IA locale. Elle est modifiable à tout moment."
      />

      <form
        className="mb-4 flex max-w-md gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          if (newName.trim()) create.mutate(newName.trim());
        }}
      >
        <Input
          aria-label="Nouvelle catégorie"
          placeholder="Nouvelle catégorie (ex : Animaux)"
          value={newName}
          maxLength={40}
          onChange={(e) => setNewName(e.target.value)}
        />
        <Button type="submit" disabled={!newName.trim() || create.isPending}>
          <Plus /> Ajouter
        </Button>
      </form>

      {error ? (
        <ErrorMessage error={error} />
      ) : isPending ? (
        <Skeleton className="h-96 w-full max-w-2xl" />
      ) : (
        <ul className="max-w-2xl divide-y rounded-xl border">
          {data.map((c) => (
            <li key={c.id} className="flex items-start justify-between gap-3 px-4 py-2.5">
              <div className="min-w-0">
                <p className="flex items-center gap-1.5 truncate font-medium">
                  {c.name}
                  {c.is_system && <Lock className="size-3.5 text-muted-foreground" aria-label="catégorie protégée" />}
                </p>
                {c.description && <p className="text-sm text-muted-foreground">{c.description}</p>}
                <p className="text-xs text-muted-foreground">
                  {c.transaction_count > 0 ? (
                    <Link href="/operations" className="hover:underline">
                      {c.transaction_count} opération{c.transaction_count > 1 ? "s" : ""}
                    </Link>
                  ) : (
                    "aucune opération"
                  )}
                </p>
              </div>
              <div className="flex shrink-0 gap-1">
                <Button variant="ghost" size="icon-sm" aria-label={`Modifier ${c.name}`} onClick={() => setRenaming(c)}>
                  <Pencil />
                </Button>
                {!c.is_system && (
                  <Button variant="ghost" size="icon-sm" aria-label={`Supprimer ${c.name}`} onClick={() => setDeleting(c)}>
                    <Trash2 />
                  </Button>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}

      <RenameDialog category={renaming} onClose={() => setRenaming(null)} />

      <Dialog open={deleting !== null} onOpenChange={(open) => !open && setDeleting(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Supprimer « {deleting?.name} » ?</DialogTitle>
            <DialogDescription>
              Ses {deleting?.transaction_count} opération(s) et les corrections associées passeront en
              « Inconnu ». Vous pourrez les reclasser ensuite.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <DialogClose render={<Button variant="outline" />}>Annuler</DialogClose>
            <Button variant="destructive" disabled={remove.isPending} onClick={() => deleting && remove.mutate(deleting.id)}>
              Supprimer
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}

function RenameDialog({ category, onClose }: { category: Category | null; onClose: () => void }) {
  const invalidate = useInvalidateData();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [editedId, setEditedId] = useState<number | null>(null);
  if (category && editedId !== category.id) {
    setEditedId(category.id);
    setName(category.name);
    setDescription(category.description ?? "");
  }
  const close = () => {
    setEditedId(null);
    onClose();
  };
  const rename = useMutation({
    mutationFn: () =>
      unwrap(
        api.PATCH("/api/categories/{category_id}", {
          params: { path: { category_id: category!.id } },
          body: { name: name.trim(), description: description.trim() || null },
        }),
      ),
    onSuccess: async () => {
      await invalidate();
      toast.success("Catégorie enregistrée");
      close();
    },
    onError: (e) => toast.error(e.message),
  });

  return (
    <Dialog open={category !== null} onOpenChange={(open) => !open && close()}>
      <DialogContent>
        <form
          className="grid gap-4"
          onSubmit={(e) => {
            e.preventDefault();
            if (name.trim()) rename.mutate();
          }}
        >
          <DialogHeader>
            <DialogTitle>Modifier la catégorie</DialogTitle>
            <DialogDescription>Les opérations et vos corrections suivent le nouveau nom.</DialogDescription>
          </DialogHeader>
          <div className="grid gap-1.5">
            <Label htmlFor="category-name">Nom</Label>
            <Input
              id="category-name"
              value={name}
              maxLength={40}
              disabled={category?.is_system}
              onChange={(e) => setName(e.target.value)}
            />
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="category-description">Ce que cette catégorie signifie pour vous</Label>
            <textarea
              id="category-description"
              value={description}
              maxLength={300}
              rows={3}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Ex : loyer, charges, et ce que ma colocataire me rembourse"
              className="w-full resize-y rounded-lg border border-input bg-transparent px-2.5 py-1.5 text-sm outline-none placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 dark:bg-input/30"
            />
            <p className="text-xs text-muted-foreground">Cette description est donnée à l&apos;IA à chaque catégorisation.</p>
          </div>
          <DialogFooter>
            <Button type="submit" disabled={!name.trim() || rename.isPending}>
              Enregistrer
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

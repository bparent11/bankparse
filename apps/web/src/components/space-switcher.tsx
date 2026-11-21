"use client";

import { useMutation } from "@tanstack/react-query";
import { Pencil } from "lucide-react";
import { useState } from "react";
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
import { api, unwrap, type Space } from "@/lib/api";
import { useInvalidateData } from "@/lib/queries";
import { useSpace } from "@/lib/space";

const NEW = "new";

/** Switch between users (one per account holder), add one, rename or remove the current one. */
export function SpaceSwitcher() {
  const { spaces, spaceId, setSpaceId } = useSpace();
  const [dialog, setDialog] = useState<"edit" | "new" | null>(null);
  if (spaces.length === 0 || spaceId === undefined) return null;
  const current = spaces.find((s) => s.id === spaceId)!;

  return (
    <div className="mb-2 md:mb-4">
      <p className="mb-1 hidden px-1 text-xs text-muted-foreground md:block">Utilisateur</p>
      <div className="flex items-center gap-1.5">
        <span
          aria-hidden
          className="flex size-7 shrink-0 items-center justify-center rounded-full bg-sidebar-accent text-[11px] font-semibold text-sidebar-accent-foreground"
        >
          {initials(current.name)}
        </span>
        <NativeSelect
          aria-label="Utilisateur affiché"
          className="min-w-0 flex-1"
          value={spaceId}
          onChange={(e) => (e.target.value === NEW ? setDialog("new") : setSpaceId(Number(e.target.value)))}
        >
          {spaces.map((s) => (
            <option key={s.id} value={s.id}>
              {s.name}
            </option>
          ))}
          <option value={NEW}>＋ Nouvel utilisateur…</option>
        </NativeSelect>
        <Button
          variant="ghost"
          size="icon-sm"
          aria-label={`Modifier ${current.name}`}
          onClick={() => setDialog("edit")}
        >
          <Pencil />
        </Button>
      </div>
      {dialog === "edit" && <EditUserDialog space={current} onClose={() => setDialog(null)} />}
      {dialog === "new" && <NewUserDialog onClose={() => setDialog(null)} onCreated={(s) => setSpaceId(s.id)} />}
    </div>
  );
}

function initials(name: string): string {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((w) => w[0]!.toUpperCase())
    .join("");
}

/** Add a user by hand, before importing their statements (also used by the Import page). */
export function NewUserDialog({ onClose, onCreated }: { onClose: () => void; onCreated: (space: Space) => void }) {
  const invalidate = useInvalidateData();
  const [name, setName] = useState("");
  const create = useMutation({
    mutationFn: () => unwrap(api.POST("/api/spaces", { body: { name } })),
    onSuccess: async (space) => {
      await invalidate();
      onCreated(space);
      toast.success(`Utilisateur « ${space.name} » ajouté`);
      onClose();
    },
    onError: (e) => toast.error(e.message),
  });

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        <form
          className="grid gap-4"
          onSubmit={(e) => {
            e.preventDefault();
            create.mutate();
          }}
        >
          <DialogHeader>
            <DialogTitle>Nouvel utilisateur</DialogTitle>
            <DialogDescription>
              Ses comptes, opérations et relevés seront séparés des vôtres. Importez ensuite ses relevés en le
              choisissant dans « Importer pour ».
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-2">
            <Label htmlFor="new-user-name">Prénom et nom</Label>
            <Input
              id="new-user-name"
              value={name}
              maxLength={60}
              placeholder="Ex : Emma Martin"
              onChange={(e) => setName(e.target.value)}
              autoFocus
            />
          </div>
          <DialogFooter>
            <Button type="submit" disabled={create.isPending || !name.trim()}>
              Ajouter
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function EditUserDialog({ space, onClose }: { space: Space; onClose: () => void }) {
  const invalidate = useInvalidateData();
  const [value, setValue] = useState(space.name);
  const save = useMutation({
    mutationFn: () =>
      unwrap(
        api.PATCH("/api/spaces/{space_id}", {
          params: { path: { space_id: space.id } },
          body: { name: value },
        }),
      ),
    onSuccess: async () => {
      await invalidate();
      toast.success("Utilisateur renommé");
      onClose();
    },
    onError: (e) => toast.error(e.message),
  });
  const remove = useMutation({
    mutationFn: () =>
      unwrap(
        api.DELETE("/api/spaces/{space_id}", {
          params: { path: { space_id: space.id } },
        }),
      ),
    onSuccess: async () => {
      await invalidate();
      toast.success(`Utilisateur « ${space.name} » retiré`);
      onClose();
    },
    onError: (e) => toast.error(e.message),
  });

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        <form
          className="grid gap-4"
          onSubmit={(e) => {
            e.preventDefault();
            save.mutate();
          }}
        >
          <DialogHeader>
            <DialogTitle>Modifier l&apos;utilisateur</DialogTitle>
            <DialogDescription>
              {space.account_count} compte{space.account_count > 1 ? "s" : ""} ·{" "}
              {space.transaction_count.toLocaleString("fr-FR")} opération
              {space.transaction_count > 1 ? "s" : ""}
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-2">
            <Label htmlFor="space-name">Nom</Label>
            <Input id="space-name" value={value} maxLength={60} onChange={(e) => setValue(e.target.value)} autoFocus />
          </div>
          <DialogFooter className="sm:justify-between">
            {space.account_count === 0 ? (
              <Button type="button" variant="destructive" disabled={remove.isPending} onClick={() => remove.mutate()}>
                Retirer cet utilisateur
              </Button>
            ) : (
              <span />
            )}
            <Button type="submit" disabled={save.isPending || !value.trim()}>
              Enregistrer
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

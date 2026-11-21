import { AlertTriangle, ShieldCheck, ShieldQuestion } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { BANK_LABELS, formatEUR, formatSignedEUR } from "@/lib/format";
import { cn } from "@/lib/utils";

export function PageHeader({
  title,
  description,
  actions,
}: {
  title: string;
  description?: React.ReactNode;
  actions?: React.ReactNode;
}) {
  return (
    <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
        {description && <p className="mt-1 text-sm text-muted-foreground">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </div>
  );
}

export function Amount({ value, signed = true, className }: { value: number; signed?: boolean; className?: string }) {
  return (
    <span
      className={cn(
        "font-mono tabular-nums whitespace-nowrap",
        signed && value > 0 && "text-positive",
        value < 0 && "text-negative",
        className,
      )}
    >
      {signed ? formatSignedEUR(value) : formatEUR(value)}
    </span>
  );
}

const BANK_STYLES: Record<string, string> = {
  CA: "bg-emerald-500/10 text-emerald-700 dark:text-emerald-300",
  CM: "bg-sky-500/10 text-sky-700 dark:text-sky-300",
  BOURSO: "bg-pink-500/10 text-pink-700 dark:text-pink-300",
  LCL: "bg-amber-500/10 text-amber-700 dark:text-amber-300",
};

export function BankBadge({ code }: { code?: string | null }) {
  if (!code) return null;
  return (
    <Badge variant="secondary" className={cn("border-transparent", BANK_STYLES[code])}>
      {BANK_LABELS[code] ?? code}
    </Badge>
  );
}

export function Stat({ label, children, className }: { label: string; children: React.ReactNode; className?: string }) {
  return (
    <div className={cn("rounded-xl border bg-card px-4 py-3 shadow-xs", className)}>
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="mt-0.5 text-lg font-semibold tabular-nums">{children}</p>
    </div>
  );
}

export function EmptyState({
  icon: Icon,
  title,
  children,
}: {
  icon: React.ComponentType<{ className?: string }>;
  title: string;
  children?: React.ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center rounded-xl border border-dashed bg-card/50 px-6 py-14 text-center">
      <span className="mb-3 flex size-12 items-center justify-center rounded-full bg-accent text-accent-foreground">
        <Icon className="size-6" />
      </span>
      <p className="font-medium">{title}</p>
      {children && <div className="mt-2 max-w-md text-sm text-muted-foreground">{children}</div>}
    </div>
  );
}

export function ErrorMessage({ error }: { error: unknown }) {
  const message = error instanceof Error ? error.message : "Erreur inconnue";
  return (
    <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive">
      Impossible de joindre l&apos;API ({message}). Vérifiez que le serveur FastAPI est lancé.
    </div>
  );
}

export function CheckBadge({ ok }: { ok?: boolean | null }) {
  if (ok === true)
    return (
      <span
        className="flex shrink-0 items-center gap-1 text-xs text-positive"
        title="Solde initial + opérations = solde final"
      >
        <ShieldCheck className="size-4" /> Soldes vérifiés
      </span>
    );
  if (ok === false)
    return (
      <span
        className="flex shrink-0 items-center gap-1 text-xs text-amber-600"
        title="Les opérations lues ne correspondent pas aux soldes du relevé"
      >
        <AlertTriangle className="size-4" /> Écart de solde
      </span>
    );
  return (
    <span
      className="flex shrink-0 items-center gap-1 text-xs text-muted-foreground"
      title="Le relevé ne contient pas les deux soldes"
    >
      <ShieldQuestion className="size-4" /> Non vérifiable
    </span>
  );
}

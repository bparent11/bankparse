"use client";

import { useMutation } from "@tanstack/react-query";
import { Landmark, Pencil } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { Area, AreaChart, YAxis } from "recharts";
import { toast } from "sonner";

import { BankBadge, EmptyState, ErrorMessage, PageHeader } from "@/components/common";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { ChartContainer, ChartTooltip, ChartTooltipContent, type ChartConfig } from "@/components/ui/chart";
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
import { Skeleton } from "@/components/ui/skeleton";
import { api, unwrap, type Account } from "@/lib/api";
import { formatDate, formatEUR } from "@/lib/format";
import { useAccounts, useBalances, useInvalidateData } from "@/lib/queries";
import { cn } from "@/lib/utils";

export function AccountsView() {
  const { data, error, isPending } = useAccounts();
  const [editing, setEditing] = useState<Account | null>(null);

  return (
    <>
      <PageHeader title="Comptes" description="Les comptes détectés dans vos relevés, avec leur dernier solde connu." />
      {error ? (
        <ErrorMessage error={error} />
      ) : isPending ? (
        <div className="grid gap-4 md:grid-cols-2">
          <Skeleton className="h-56" />
          <Skeleton className="h-56" />
        </div>
      ) : data.length === 0 ? (
        <EmptyState icon={Landmark} title="Aucun compte pour le moment">
          Les comptes apparaissent automatiquement quand vous{" "}
          <Link href="/import" className="underline underline-offset-4">
            importez des relevés
          </Link>
          .
        </EmptyState>
      ) : (
        <div className="grid gap-4 md:grid-cols-2">
          {data.map((account) => (
            <AccountCard key={account.id} account={account} onRename={() => setEditing(account)} />
          ))}
        </div>
      )}
      <RenameDialog account={editing} onClose={() => setEditing(null)} />
    </>
  );
}

function AccountCard({ account, onRename }: { account: Account; onRename: () => void }) {
  return (
    <Card>
      <CardHeader>
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <div className="mb-1.5 flex items-center gap-2">
              <BankBadge code={account.bank_code} />
              <span className="font-mono text-xs text-muted-foreground">n° {account.account_number}</span>
            </div>
            <CardTitle className="truncate">{account.label}</CardTitle>
            {account.label !== account.statement_label && (
              <CardDescription className="truncate">{account.statement_label}</CardDescription>
            )}
          </div>
          <Button variant="ghost" size="icon-sm" aria-label={`Renommer ${account.label}`} onClick={onRename}>
            <Pencil />
          </Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <div>
          <p
            className={cn(
              "font-mono text-2xl font-semibold tabular-nums",
              (account.last_balance ?? 0) < 0 && "text-negative",
            )}
          >
            {account.last_balance != null ? formatEUR(account.last_balance) : "—"}
          </p>
          <p className="text-xs text-muted-foreground">
            {account.last_balance_date ? `solde au ${formatDate(account.last_balance_date)}` : "solde inconnu"}
          </p>
        </div>
        <BalanceSparkline accountId={account.id} />
        <div className="flex flex-wrap items-center justify-between gap-2 text-sm text-muted-foreground">
          <span>
            {account.transaction_count} opération{account.transaction_count > 1 ? "s" : ""}
            {account.first_operation && ` · ${formatDate(account.first_operation)} → ${formatDate(account.last_operation)}`}
          </span>
          {account.transaction_count > 0 && (
            <Button variant="link" size="sm" className="px-0" render={<Link href={`/operations?account=${account.id}`} />}>
              Voir les opérations
            </Button>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

const sparkConfig = { amount: { label: "Solde", color: "var(--chart-2)" } } satisfies ChartConfig;

function BalanceSparkline({ accountId }: { accountId: number }) {
  const { data } = useBalances(accountId);
  if (!data) return <Skeleton className="h-16" />;
  if (data.length < 2) return <div className="h-16" aria-hidden />;
  return (
    <ChartContainer config={sparkConfig} className="aspect-auto h-16 w-full" aria-label="Évolution du solde">
      <AreaChart data={data} margin={{ top: 4, right: 0, bottom: 0, left: 0 }}>
        <YAxis hide domain={["auto", "auto"]} />
        <ChartTooltip
          cursor={false}
          content={
            <ChartTooltipContent
              hideIndicator
              labelFormatter={(_, payload) => formatDate(payload?.[0]?.payload?.date)}
              formatter={(value) => formatEUR(Number(value))}
            />
          }
        />
        <Area
          dataKey="amount"
          type="monotone"
          stroke="var(--color-amount)"
          fill="var(--color-amount)"
          fillOpacity={0.12}
          strokeWidth={1.5}
          isAnimationActive={false}
        />
      </AreaChart>
    </ChartContainer>
  );
}

function RenameDialog({ account, onClose }: { account: Account | null; onClose: () => void }) {
  const invalidate = useInvalidateData();
  const [label, setLabel] = useState("");
  const [editedId, setEditedId] = useState<number | null>(null);
  if (account && editedId !== account.id) {
    // Reset the field when a different account is opened (no effect needed).
    setEditedId(account.id);
    setLabel(account.label);
  }

  const save = useMutation({
    mutationFn: (value: string) =>
      unwrap(
        api.PATCH("/api/accounts/{account_id}", {
          params: { path: { account_id: account!.id } },
          body: { label: value },
        }),
      ),
    onSuccess: async () => {
      await invalidate();
      toast.success("Compte renommé");
      onClose();
    },
    onError: (e) => toast.error(e.message),
  });

  return (
    <Dialog
      open={account !== null}
      onOpenChange={(open) => {
        if (!open) {
          onClose();
          setEditedId(null);
        }
      }}
    >
      <DialogContent>
        <form
          className="grid gap-4"
          onSubmit={(e) => {
            e.preventDefault();
            save.mutate(label);
          }}
        >
          <DialogHeader>
            <DialogTitle>Renommer le compte</DialogTitle>
            <DialogDescription>
              Nom lu sur les relevés : {account?.statement_label}. Laissez vide pour revenir à ce nom.
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-2">
            <Label htmlFor="account-label">Nom affiché</Label>
            <Input id="account-label" value={label} onChange={(e) => setLabel(e.target.value)} autoFocus />
          </div>
          <DialogFooter>
            <Button type="submit" disabled={save.isPending}>
              Enregistrer
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

"use client";

import { FileUp, Upload } from "lucide-react";
import Link from "next/link";
import { Bar, BarChart, CartesianGrid, XAxis, YAxis } from "recharts";

import { Amount, BankBadge, EmptyState, ErrorMessage, PageHeader } from "@/components/common";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import {
  ChartContainer,
  ChartLegend,
  ChartLegendContent,
  ChartTooltip,
  ChartTooltipContent,
  type ChartConfig,
} from "@/components/ui/chart";
import { Skeleton } from "@/components/ui/skeleton";
import { formatCompactEUR, formatDate, formatEUR, formatMonth } from "@/lib/format";
import { useAccounts, useSummary } from "@/lib/queries";

const chartConfig = {
  credit: { label: "Entrées", color: "var(--positive)" },
  debit: { label: "Sorties", color: "var(--negative)" },
} satisfies ChartConfig;

export function OverviewView() {
  const summary = useSummary();
  const accounts = useAccounts();

  if (summary.error) return <ErrorMessage error={summary.error} />;
  if (summary.isPending)
    return (
      <div className="space-y-4">
        <Skeleton className="h-10 w-64" />
        <div className="grid gap-4 sm:grid-cols-3">
          <Skeleton className="h-24" />
          <Skeleton className="h-24" />
          <Skeleton className="h-24" />
        </div>
        <Skeleton className="h-80" />
      </div>
    );

  const s = summary.data;
  if (s.transactions === 0)
    return (
      <>
        <PageHeader title="Bienvenue 👋" description="Vos relevés bancaires, enfin lisibles." />
        <EmptyState icon={FileUp} title="Aucune opération pour le moment">
          <p>Importez vos relevés PDF (Crédit Agricole, Crédit Mutuel, Boursorama) pour retrouver toutes vos opérations ici.</p>
          <Button className="mt-4" render={<Link href="/import" />}>
            <Upload /> Importer des relevés
          </Button>
        </EmptyState>
      </>
    );

  // Last 12 months with data; debits shown as positive bars next to credits.
  const months = s.months.slice(-12).map((m) => ({ month: m.month, credit: m.credit, debit: -m.debit }));
  const last = months.at(-1);

  return (
    <>
      <PageHeader
        title="Vue d'ensemble"
        description={`Du ${formatDate(s.first_operation)} au ${formatDate(s.last_operation)}`}
        actions={
          <Button size="sm" render={<Link href="/import" />}>
            <Upload /> Importer
          </Button>
        }
      />

      <div className="mb-6 grid gap-4 sm:grid-cols-3">
        <Stat label="Opérations" value={s.transactions.toLocaleString("fr-FR")} href="/operations" />
        <Stat label="Comptes" value={String(s.accounts)} href="/comptes" />
        <Stat
          label="Relevés lus"
          value={s.files === s.files_total ? String(s.files) : `${s.files} / ${s.files_total}`}
          hint={s.files === s.files_total ? undefined : `${s.files_total - s.files} fichier(s) non lu(s)`}
          href="/fichiers"
        />
      </div>

      <Card className="mb-6">
        <CardHeader>
          <CardTitle>Entrées et sorties par mois</CardTitle>
          <CardDescription>
            {last && (
              <>
                {formatMonth(last.month)} : entrées <Amount value={last.credit} />, sorties <Amount value={-last.debit} />
              </>
            )}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <ChartContainer config={chartConfig} className="aspect-auto h-72 w-full">
            <BarChart data={months} margin={{ left: 4, right: 4 }}>
              <CartesianGrid vertical={false} />
              <XAxis dataKey="month" tickLine={false} axisLine={false} tickFormatter={formatMonth} tickMargin={8} />
              <YAxis tickLine={false} axisLine={false} width={64} tickFormatter={(v) => formatCompactEUR(Number(v))} />
              <ChartTooltip
                content={
                  <ChartTooltipContent
                    labelFormatter={(value) => formatMonth(String(value))}
                    formatter={(value, name) => (
                      <div className="flex w-full justify-between gap-4">
                        <span className="text-muted-foreground">{chartConfig[name as keyof typeof chartConfig]?.label}</span>
                        <span className="font-mono tabular-nums">{formatEUR(Number(value))}</span>
                      </div>
                    )}
                  />
                }
              />
              <ChartLegend content={<ChartLegendContent />} />
              <Bar dataKey="credit" fill="var(--color-credit)" radius={[4, 4, 0, 0]} isAnimationActive={false} />
              <Bar dataKey="debit" fill="var(--color-debit)" radius={[4, 4, 0, 0]} isAnimationActive={false} />
            </BarChart>
          </ChartContainer>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Soldes</CardTitle>
          <CardDescription>Dernier solde connu de chaque compte</CardDescription>
        </CardHeader>
        <CardContent>
          <ul className="divide-y">
            {accounts.data?.map((a) => (
              <li key={a.id} className="flex items-center justify-between gap-3 py-2.5">
                <div className="min-w-0">
                  <Link href={`/operations?account=${a.id}`} className="block truncate font-medium hover:underline">
                    {a.label}
                  </Link>
                  <div className="mt-0.5 flex items-center gap-2 text-xs text-muted-foreground">
                    <BankBadge code={a.bank_code} />
                    {a.last_balance_date && <span>au {formatDate(a.last_balance_date)}</span>}
                  </div>
                </div>
                {a.last_balance != null ? (
                  <Amount value={a.last_balance} signed={false} className="font-medium" />
                ) : (
                  <span className="text-muted-foreground">—</span>
                )}
              </li>
            ))}
          </ul>
        </CardContent>
      </Card>
    </>
  );
}

function Stat({ label, value, href, hint }: { label: string; value: string; href: string; hint?: string }) {
  return (
    <Link href={href} className="rounded-xl border bg-card p-4 transition-colors hover:bg-muted/50">
      <p className="text-sm text-muted-foreground">{label}</p>
      <p className="mt-1 text-2xl font-semibold tabular-nums">{value}</p>
      {hint && <p className="text-xs text-muted-foreground">{hint}</p>}
    </Link>
  );
}

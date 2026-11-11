const eur = new Intl.NumberFormat("fr-FR", { style: "currency", currency: "EUR" });
const eurSigned = new Intl.NumberFormat("fr-FR", { style: "currency", currency: "EUR", signDisplay: "exceptZero" });
const eurCompact = new Intl.NumberFormat("fr-FR", {
  style: "currency",
  currency: "EUR",
  notation: "compact",
  maximumFractionDigits: 1,
});
const longDate = new Intl.DateTimeFormat("fr-FR", { day: "2-digit", month: "short", year: "numeric", timeZone: "UTC" });
const shortDate = new Intl.DateTimeFormat("fr-FR", { day: "2-digit", month: "2-digit", year: "numeric", timeZone: "UTC" });
const monthFmt = new Intl.DateTimeFormat("fr-FR", { month: "short", year: "2-digit", timeZone: "UTC" });

export const formatEUR = (value: number) => eur.format(value);
export const formatSignedEUR = (value: number) => eurSigned.format(value);
export const formatCompactEUR = (value: number) => eurCompact.format(value);

/** ISO date ("2025-01-31") -> "31 janv. 2025". Dates are parsed as UTC to avoid timezone shifts. */
export const formatDate = (iso?: string | null) => (iso ? longDate.format(new Date(`${iso.slice(0, 10)}T00:00:00Z`)) : "—");
export const formatShortDate = (iso?: string | null) =>
  iso ? shortDate.format(new Date(`${iso.slice(0, 10)}T00:00:00Z`)) : "—";
/** "2025-01" -> "janv. 25" */
export const formatMonth = (yyyymm: string) => monthFmt.format(new Date(`${yyyymm}-01T00:00:00Z`));

export const BANK_LABELS: Record<string, string> = {
  CA: "Crédit Agricole",
  CM: "Crédit Mutuel",
  BOURSO: "Boursorama",
};

export const formatBytes = (bytes: number) =>
  bytes < 1024 * 1024 ? `${Math.round(bytes / 1024)} Ko` : `${(bytes / 1024 / 1024).toFixed(1)} Mo`;

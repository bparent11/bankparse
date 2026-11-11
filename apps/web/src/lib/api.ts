import createClient from "openapi-fetch";

import type { components, paths } from "./api-types";

/** Typed client for the FastAPI backend (same origin, proxied by Next.js rewrites). */
export const api = createClient<paths>({ baseUrl: "" });

export type Schemas = components["schemas"];
export type Account = Schemas["AccountOut"];
export type Transaction = Schemas["TransactionOut"];
export type TransactionPage = Schemas["TransactionPage"];
export type StatementFile = Schemas["FileOut"];
export type ImportResult = Schemas["ImportResultOut"];
export type Summary = Schemas["Summary"];
export type Balance = Schemas["BalanceOut"];

export type TransactionQuery = NonNullable<paths["/api/transactions"]["get"]["parameters"]["query"]>;

/** Unwrap an openapi-fetch result or throw a readable error (used inside TanStack Query functions). */
export async function unwrap<T>(promise: Promise<{ data?: T; error?: unknown; response: Response }>): Promise<T> {
  const { data, error, response } = await promise;
  if (error !== undefined || data === undefined) {
    if (response.status === 204) return undefined as T;
    const detail = (error as { detail?: unknown } | undefined)?.detail;
    throw new Error(typeof detail === "string" ? detail : `Erreur ${response.status}`);
  }
  return data;
}

/** Build a query string, dropping empty values and repeating array values (account_id=1&account_id=2). */
export function toQueryString(params: Record<string, unknown>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === "") continue;
    if (Array.isArray(value)) value.forEach((v) => search.append(key, String(v)));
    else search.append(key, String(value));
  }
  return search.toString();
}

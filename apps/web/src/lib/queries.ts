"use client";

import { keepPreviousData, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, unwrap, type TransactionQuery } from "./api";

export const keys = {
  summary: ["summary"] as const,
  accounts: ["accounts"] as const,
  balances: (id: number) => ["accounts", id, "balances"] as const,
  files: ["files"] as const,
  transactions: (q: TransactionQuery) => ["transactions", q] as const,
};

export const useSummary = () => useQuery({ queryKey: keys.summary, queryFn: () => unwrap(api.GET("/api/summary")) });

export const useAccounts = () =>
  useQuery({ queryKey: keys.accounts, queryFn: () => unwrap(api.GET("/api/accounts")) });

export const useBalances = (accountId: number) =>
  useQuery({
    queryKey: keys.balances(accountId),
    queryFn: () =>
      unwrap(api.GET("/api/accounts/{account_id}/balances", { params: { path: { account_id: accountId } } })),
  });

export const useFiles = () => useQuery({ queryKey: keys.files, queryFn: () => unwrap(api.GET("/api/files")) });

export const useTransactions = (query: TransactionQuery) =>
  useQuery({
    queryKey: keys.transactions(query),
    queryFn: () => unwrap(api.GET("/api/transactions", { params: { query } })),
    placeholderData: keepPreviousData,
  });

/** Everything derived from imported files: call after an upload, a delete or a reparse. */
export function useInvalidateData() {
  const client = useQueryClient();
  return () =>
    Promise.all(
      [keys.summary, keys.accounts, keys.files, ["transactions"]].map((queryKey) =>
        client.invalidateQueries({ queryKey }),
      ),
    );
}

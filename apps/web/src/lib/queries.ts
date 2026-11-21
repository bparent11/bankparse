"use client";

import { keepPreviousData, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, unwrap, type TransactionQuery } from "./api";
import { spacesKey, useSpace } from "./space";

type SpaceId = number | undefined;

/** Every data key starts with its resource and ends with the space, so a whole resource can be invalidated. */
export const keys = {
  summary: (space: SpaceId) => ["summary", space] as const,
  accounts: (space: SpaceId) => ["accounts", space] as const,
  balances: (id: number) => ["balances", id] as const,
  files: (space: SpaceId) => ["files", space] as const,
  transactions: (q: TransactionQuery) => ["transactions", q] as const,
};

export const useSummary = () => {
  const { spaceId, ready } = useSpace();
  return useQuery({
    queryKey: keys.summary(spaceId),
    queryFn: () => unwrap(api.GET("/api/summary", { params: { query: { space_id: spaceId } } })),
    enabled: ready,
  });
};

export const useAccounts = () => {
  const { spaceId, ready } = useSpace();
  return useQuery({
    queryKey: keys.accounts(spaceId),
    queryFn: () => unwrap(api.GET("/api/accounts", { params: { query: { space_id: spaceId } } })),
    enabled: ready,
  });
};

export const useBalances = (accountId: number) =>
  useQuery({
    queryKey: keys.balances(accountId),
    queryFn: () =>
      unwrap(api.GET("/api/accounts/{account_id}/balances", { params: { path: { account_id: accountId } } })),
  });

export const useFiles = () => {
  const { spaceId, ready } = useSpace();
  return useQuery({
    queryKey: keys.files(spaceId),
    queryFn: () => unwrap(api.GET("/api/files", { params: { query: { space_id: spaceId } } })),
    enabled: ready,
  });
};

/** Operations of the current space (``space_id`` is added here, callers only pass their filters). */
export const useTransactions = (filters: Omit<TransactionQuery, "space_id">, enabled = true) => {
  const { spaceId, ready } = useSpace();
  const query = { ...filters, space_id: spaceId };
  return useQuery({
    queryKey: keys.transactions(query),
    queryFn: () => unwrap(api.GET("/api/transactions", { params: { query } })),
    placeholderData: keepPreviousData,
    enabled: ready && enabled,
  });
};

// ---------------------------------------------------------------- categorization (local LLM)
/** Categories are shared by every space; their operation counts are those of the current space. */
export const useCategories = () => {
  const { spaceId, ready } = useSpace();
  return useQuery({
    queryKey: ["categories", spaceId],
    queryFn: () => unwrap(api.GET("/api/categories", { params: { query: { space_id: spaceId } } })),
    enabled: ready,
  });
};

export const useCategorizeStatus = () => {
  const { spaceId, ready } = useSpace();
  return useQuery({
    queryKey: ["categorize", "status", spaceId],
    queryFn: () => unwrap(api.GET("/api/categorize/status", { params: { query: { space_id: spaceId } } })),
    staleTime: 5_000,
    enabled: ready,
  });
};

/** Latest categorization job of the current space, polled every 2 s while it runs. */
export const useLatestCategorizeJob = () => {
  const { spaceId, ready } = useSpace();
  return useQuery({
    queryKey: ["categorize", "latest", spaceId],
    queryFn: () => unwrap(api.GET("/api/categorize/jobs/latest", { params: { query: { space_id: spaceId } } })),
    refetchInterval: (query) => (query.state.data?.status === "running" ? 2000 : false),
    staleTime: 0,
    enabled: ready,
  });
};

/** Everything derived from imported files: call after an upload, a delete, a reparse or a move. */
export function useInvalidateData() {
  const client = useQueryClient();
  return () =>
    Promise.all(
      [spacesKey, ["summary"], ["accounts"], ["balances"], ["files"], ["transactions"], ["categories"], ["categorize", "status"]].map(
        (queryKey) => client.invalidateQueries({ queryKey }),
      ),
    );
}

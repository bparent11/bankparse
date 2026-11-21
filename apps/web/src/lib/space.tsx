"use client";

import { useQuery } from "@tanstack/react-query";
import { createContext, useCallback, useContext, useMemo, useState } from "react";

import { api, unwrap, type Space } from "./api";

/** One space per account holder (detected on the statements). The chosen one is remembered in this browser. */
type SpaceContextValue = {
  spaces: Space[];
  /** Current space, undefined while loading or when nothing is imported yet (the API then returns everything). */
  spaceId: number | undefined;
  /** False until the spaces are loaded: data queries wait for it so they are not fetched twice. */
  ready: boolean;
  setSpaceId: (id: number) => void;
};

const STORAGE_KEY = "bankparse.space";
const SpaceContext = createContext<SpaceContextValue | null>(null);

function readStored(): number | undefined {
  try {
    const value = Number(window.localStorage.getItem(STORAGE_KEY));
    return Number.isInteger(value) && value > 0 ? value : undefined;
  } catch {
    return undefined;
  }
}

export const spacesKey = ["spaces"] as const;

export function SpaceProvider({ children }: { children: React.ReactNode }) {
  const query = useQuery({ queryKey: spacesKey, queryFn: () => unwrap(api.GET("/api/spaces")) });
  const [chosen, setChosen] = useState<number | undefined>(() =>
    typeof window === "undefined" ? undefined : readStored(),
  );

  const spaces = useMemo(() => query.data ?? [], [query.data]);
  // A remembered space may have disappeared (its accounts were moved or deleted): fall back to the first one.
  const spaceId = spaces.some((s) => s.id === chosen) ? chosen : spaces[0]?.id;

  const setSpaceId = useCallback((id: number) => {
    setChosen(id);
    try {
      window.localStorage.setItem(STORAGE_KEY, String(id));
    } catch {
      // private window or blocked storage: the choice just lasts for this tab
    }
  }, []);

  const value = useMemo(
    () => ({ spaces, spaceId, ready: !query.isPending, setSpaceId }),
    [spaces, spaceId, query.isPending, setSpaceId],
  );
  return <SpaceContext.Provider value={value}>{children}</SpaceContext.Provider>;
}

export function useSpace(): SpaceContextValue {
  const value = useContext(SpaceContext);
  if (value === null) throw new Error("useSpace must be used inside <SpaceProvider>");
  return value;
}

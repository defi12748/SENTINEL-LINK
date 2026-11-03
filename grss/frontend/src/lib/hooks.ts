"use client";

import { useEffect, useState } from "react";

/** Fetch once on mount (and when deps change); null while loading. */
export function useApi<T>(load: () => Promise<T>, deps: unknown[] = []): { data: T | null; error: string | null } {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let alive = true;
    setData(null);
    setError(null);
    load().then(d => alive && setData(d)).catch(e => alive && setError(String(e)));
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  return { data, error };
}

export { PHOTOS, PHOTO_LIST, fmtDay, fmtLong } from "./photos";

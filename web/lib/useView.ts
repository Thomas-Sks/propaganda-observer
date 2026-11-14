"use client";
import { useEffect, useState } from "react";
import { useOps } from "./store";

/** Charge une vue et la recharge quand des données live arrivent (store.version). */
export function useView<T>(load: () => Promise<T>, deps: unknown[]): { data: T | null; error: string | null } {
  const version = useOps((s) => s.version);
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let live = true;
    load().then((d) => { if (live) { setData(d); setError(null); } }).catch((e) => live && setError(String(e)));
    return () => { live = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [version, ...deps]);
  return { data, error };
}

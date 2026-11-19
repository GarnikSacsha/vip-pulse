import { useCallback, useEffect, useState } from "react";
import { ApiError } from "../api/client";

export interface ApiState<T> {
  data: T | null;
  error: string | null;
  loading: boolean;
  reload: () => void;
}

interface Settled<T> {
  request: string;
  data: T | null;
  error: string | null;
}

/**
 * Loads `load()` whenever `key` changes or `reload()` is called.
 * `loading` is derived: true until the latest request settles. Responses to outdated
 * requests are ignored, and the previous data stays visible while reloading.
 */
export function useApi<T>(load: () => Promise<T>, key: string): ApiState<T> {
  const [version, setVersion] = useState(0);
  const [settled, setSettled] = useState<Settled<T> | null>(null);
  const request = `${key}#${version}`;

  useEffect(() => {
    let current = true;
    load().then(
      (data) => {
        if (current) setSettled({ request, data, error: null });
      },
      (e: unknown) => {
        if (!current) return;
        const error = e instanceof ApiError ? e.message : "Не удалось связаться с сервером";
        setSettled((prev) => ({ request, data: prev?.data ?? null, error }));
      },
    );
    return () => {
      current = false;
    };
    // `load` is recreated on every render; `request` identifies what is being loaded.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [request]);

  const reload = useCallback(() => setVersion((v) => v + 1), []);
  return {
    data: settled?.data ?? null,
    error: settled?.request === request ? settled.error : null,
    loading: settled?.request !== request,
    reload,
  };
}

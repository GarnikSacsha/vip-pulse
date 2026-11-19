import { useCallback, useEffect, useState } from "react";
import { ApiError } from "../api/client";

export interface ApiState<T> {
  data: T | null;
  error: string | null;
  /** HTTP status of the failed request, when the server answered. */
  errorStatus: number | null;
  loading: boolean;
  reload: () => void;
}

interface Settled<T> {
  key: string;
  request: string;
  data: T | null;
  error: string | null;
  errorStatus: number | null;
}

/**
 * Loads `load()` whenever `key` changes or `reload()` is called.
 * `loading` is derived: true until the latest request settles. Responses to outdated
 * requests are ignored. While the same key reloads its data stays visible; data of another key
 * is never shown, so a page cannot act on the previous item while the next one loads.
 */
export function useApi<T>(load: () => Promise<T>, key: string): ApiState<T> {
  const [version, setVersion] = useState(0);
  const [settled, setSettled] = useState<Settled<T> | null>(null);
  const request = `${key}#${version}`;

  useEffect(() => {
    let current = true;
    load().then(
      (data) => {
        if (current) setSettled({ key, request, data, error: null, errorStatus: null });
      },
      (e: unknown) => {
        if (!current) return;
        const error = e instanceof ApiError ? e.message : "Не удалось связаться с сервером";
        const errorStatus = e instanceof ApiError ? e.status : null;
        setSettled((prev) => ({
          key,
          request,
          data: prev?.key === key ? prev.data : null,
          error,
          errorStatus,
        }));
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
    data: settled?.key === key ? settled.data : null,
    error: settled?.request === request ? settled.error : null,
    errorStatus: settled?.request === request ? settled.errorStatus : null,
    loading: settled?.request !== request,
    reload,
  };
}

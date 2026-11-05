import { useCallback, useEffect, useState } from "react";
import { get } from "./api";

export interface ApiState<T> { data: T | null; error: string | null; loading: boolean; reload: () => void; setData: (d: T) => void }

/** Fetch JSON for a path; re-fetches when the path or any dependency changes. */
export function useApi<T>(path: string | null, deps: unknown[] = []): ApiState<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState<boolean>(!!path);
  const [n, setN] = useState(0);

  useEffect(() => {
    if (!path) {
      setLoading(false);
      return;
    }
    const ctl = new AbortController();
    setLoading(true); // pages keep showing previous data while refreshing (see <Async>)
    get<T>(path, ctl.signal)
      .then((d) => {
        setData(d);
        setError(null);
      })
      .catch((e: Error) => {
        if (e.name !== "AbortError") setError(e.message);
      })
      .finally(() => {
        if (!ctl.signal.aborted) setLoading(false);
      });
    return () => ctl.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path, n, ...deps]);

  const reload = useCallback(() => setN((x) => x + 1), []);
  return { data, error, loading, reload, setData };
}

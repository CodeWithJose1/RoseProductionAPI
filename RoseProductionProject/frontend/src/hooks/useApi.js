import { useCallback, useEffect, useRef, useState } from 'react';

/**
 * Runs an async loader and tracks { data, loading, error }.
 * `deps` re-run the loader; `reload()` re-runs it on demand.
 */
export function useApi(loader, deps = []) {
  const [state, setState] = useState({ data: null, loading: true, error: null });
  const requestId = useRef(0);
  const loaderRef = useRef(loader);
  loaderRef.current = loader;

  const run = useCallback(async () => {
    const id = ++requestId.current;
    setState((prev) => ({ ...prev, loading: true, error: null }));
    try {
      const data = await loaderRef.current();
      if (id === requestId.current) setState({ data, loading: false, error: null });
      return data;
    } catch (error) {
      if (id === requestId.current) setState((prev) => ({ ...prev, loading: false, error }));
      return null;
    }
  }, []);

  useEffect(() => {
    run();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  return { ...state, reload: run };
}

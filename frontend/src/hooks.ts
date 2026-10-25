import { DependencyList, useEffect, useState } from "react";
import { ApiError } from "./api";

export interface Async<T> { data?: T; error?: ApiError; loading: boolean }

export function useAsync<T>(fn: () => Promise<T>, deps: DependencyList): Async<T> {
  const [state, setState] = useState<Async<T>>({ loading: true });
  useEffect(() => {
    let live = true;
    setState({ loading: true });
    fn().then(
      (data) => live && setState({ data, loading: false }),
      (e) => live && setState({ error: e instanceof ApiError ? e : new ApiError(0, "ERROR", String(e)), loading: false }),
    );
    return () => { live = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  return state;
}

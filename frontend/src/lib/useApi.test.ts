import { act, renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { useApi } from "./useApi";

function deferred<T>() {
  let resolve: (value: T) => void = () => {};
  const promise = new Promise<T>((r) => {
    resolve = r;
  });
  return { promise, resolve };
}

describe("useApi", () => {
  it("never shows data of a previous key while the new key loads", async () => {
    const first = deferred<string>();
    const second = deferred<string>();
    const loaders: Record<string, Promise<string>> = { a: first.promise, b: second.promise };
    const { result, rerender } = renderHook(({ k }) => useApi(() => loaders[k] ?? Promise.reject(), k), {
      initialProps: { k: "a" },
    });

    await act(async () => first.resolve("conversation A"));
    expect(result.current.data).toBe("conversation A");

    rerender({ k: "b" });
    expect(result.current.loading).toBe(true);
    expect(result.current.data).toBeNull(); // not "conversation A"

    await act(async () => second.resolve("conversation B"));
    expect(result.current.data).toBe("conversation B");
  });

  it("keeps the current data visible while reloading the same key", async () => {
    let n = 0;
    const { result } = renderHook(() => useApi(() => Promise.resolve(`v${++n}`), "same"));
    await waitFor(() => expect(result.current.data).toBe("v1"));

    act(() => result.current.reload());
    expect(result.current.loading).toBe(true);
    expect(result.current.data).toBe("v1");
    await waitFor(() => expect(result.current.data).toBe("v2"));
  });
});

import { describe, expect, it, vi } from "vitest";
import { ApiError, api } from "./client";

function mockFetch(status: number, body: unknown) {
  return vi.spyOn(globalThis, "fetch").mockResolvedValue(
    new Response(JSON.stringify(body), {
      status,
      headers: { "Content-Type": "application/json" },
    }),
  );
}

describe("api client", () => {
  it("sends repeated query params for multi-value filters", async () => {
    const fetchMock = mockFetch(200, []);
    await api.queue({ status: ["open", "in_progress"], priority: ["P0"] });
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/queue?status=open&status=in_progress&priority=P0",
      expect.objectContaining({ headers: expect.any(Object) }),
    );
  });

  it("omits the query string when there are no filters", async () => {
    const fetchMock = mockFetch(200, []);
    await api.queue({});
    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/queue");
  });

  it("sends status changes as JSON PATCH", async () => {
    const fetchMock = mockFetch(200, { task_id: 7, status: "resolved" });
    await api.updateTask(7, { status: "resolved", note: "Готово" });
    const [url, init] = fetchMock.mock.calls[0] ?? [];
    expect(url).toBe("/api/tasks/7");
    expect(init?.method).toBe("PATCH");
    expect(JSON.parse(String(init?.body))).toEqual({ status: "resolved", note: "Готово" });
  });

  it("turns error responses into ApiError with the server detail", async () => {
    mockFetch(409, { detail: "cannot move a task from no_action to resolved" });
    const error = await api.updateTask(1, { status: "resolved" }).catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).status).toBe(409);
    expect((error as ApiError).message).toBe("cannot move a task from no_action to resolved");
  });

  it("uses a generic message when the error body is not JSON", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response("<html>502</html>", { status: 502 }));
    const error = (await api.meta().catch((e: unknown) => e)) as ApiError;
    expect(error.status).toBe(502);
    expect(error.message).toBe("Сервер недоступен (502)");
  });
});

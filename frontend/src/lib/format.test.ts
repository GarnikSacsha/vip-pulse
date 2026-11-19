import { describe, expect, it } from "vitest";
import { formatDateTime, formatShort, formatWait } from "./format";

describe("format", () => {
  it.each([
    [null, "—"],
    [0.2, "12 мин"],
    [0.001, "1 мин"],
    [6, "6 ч"],
    [23.6, "1 д"],
    [27, "1 д 3 ч"],
    [74, "3 д 2 ч"],
  ])("formatWait(%s) = %s", (hours, expected) => {
    expect(formatWait(hours)).toBe(expected);
  });

  it("formats dates in UTC with Russian month names", () => {
    expect(formatDateTime("2026-11-12T13:00:00Z")).toBe("12 ноября 2026, 13:00 UTC");
    expect(formatShort("2026-03-01T07:05:00Z")).toBe("1 мар, 07:05");
  });
});

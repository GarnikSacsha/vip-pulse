import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Pulse } from "./Pulse";

describe("pulse indicator", () => {
  it("fills with the share of the SLA already waited", () => {
    render(<Pulse lane="waiting" waitHours={1} slaHours={4} />);
    const ring = screen.getByRole("img");
    expect(ring).toHaveAttribute("data-fill", "0.25");
    expect(ring).toHaveAccessibleName("Ждёт 1 ч из 4 ч по SLA");
    expect(ring).toHaveAttribute("data-animated", "false");
  });

  it("pulses only when the SLA is about to be breached", () => {
    render(<Pulse lane="at_risk" waitHours={3.5} slaHours={4} />);
    const ring = screen.getByRole("img");
    expect(ring).toHaveAttribute("data-animated", "true");
    expect(ring).toHaveAccessibleName("Ждёт 4 ч из 4 ч по SLA, скоро нарушение");
  });

  it("is solid and still after a breach", () => {
    render(<Pulse lane="breached" waitHours={27} slaHours={4} />);
    const ring = screen.getByRole("img");
    expect(ring).toHaveAttribute("data-fill", "1");
    expect(ring).toHaveAttribute("data-animated", "false");
    expect(ring).toHaveAccessibleName("Ждёт 1 д 3 ч из 4 ч по SLA, SLA нарушен");
  });

  it("is empty when nobody waits", () => {
    render(<Pulse lane="ok" waitHours={null} slaHours={4} />);
    const ring = screen.getByRole("img");
    expect(ring).toHaveAttribute("data-fill", "0");
    expect(ring).toHaveAccessibleName("Игрок не ждёт ответа");
  });
});

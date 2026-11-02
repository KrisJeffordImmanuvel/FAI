import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { ErrorState, LevelBadge, Modal } from "../components/ui";
import { RuleTrace, ScoreBreakdown } from "../components/explain";

describe("accessible UI components", () => {
  it("LevelBadge shows the level as text, not colour alone", () => {
    render(<LevelBadge level="Critical" score={81.2} />);
    expect(screen.getByText("Critical")).toBeInTheDocument();
    expect(screen.getByText("81.2")).toBeInTheDocument();
  });

  it("ErrorState is announced and offers a retry", () => {
    const retry = vi.fn();
    render(<ErrorState message="Server down" onRetry={retry} />);
    expect(screen.getByRole("alert")).toHaveTextContent("Server down");
    fireEvent.click(screen.getByRole("button", { name: /try again/i }));
    expect(retry).toHaveBeenCalledOnce();
  });

  it("Modal is a labelled dialog that closes on Escape", () => {
    const close = vi.fn();
    render(<Modal open onClose={close} title="Fine statement"><p>Body</p></Modal>);
    expect(screen.getByRole("dialog", { name: "Fine statement" })).toBeInTheDocument();
    fireEvent.keyDown(document, { key: "Escape" });
    expect(close).toHaveBeenCalled();
  });
});

describe("explanation components", () => {
  it("RuleTrace shows the IF conditions and the asserted fact", () => {
    render(<RuleTrace firings={[{ iteration: 2, rule_code: "R04_HIGH_RECALL", rule_name: "Overdue AND reserved", asserted: "HIGH_RECALL_PRIORITY",
      matched: [{ condition: "OVERDUE is true", field: "OVERDUE", actual: true }, { condition: "IN_DEMAND is true", field: "IN_DEMAND", actual: true }] }]} />);
    expect(screen.getByText("R04_HIGH_RECALL")).toBeInTheDocument();
    expect(screen.getByText("HIGH_RECALL_PRIORITY")).toBeInTheDocument();
    expect(screen.getByText("OVERDUE is true")).toBeInTheDocument();
  });

  it("ScoreBreakdown lists each weighted factor", () => {
    render(<ScoreBreakdown score={54.5} items={[
      { factor: "urgency", label: "Urgency of the notification type", raw: "recall", normalised: 1, weight: 25, contribution: 25 },
      { factor: "overdue", label: "Days overdue (30+ days = max)", raw: 15, normalised: 0.5, weight: 20, contribution: 10 },
    ]} />);
    expect(screen.getByText("54.5")).toBeInTheDocument();
    expect(screen.getByText("Urgency of the notification type")).toBeInTheDocument();
  });
});

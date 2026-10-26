import { describe, expect, it } from "vitest";
import type { Schema } from "../shared/api/client";
import { groupQueue } from "./queueGroups";

type Row = Schema["StaffApplicationList"];
function row(id: string, created_at: string): Row {
  return { id, created_at, updated_at: created_at, assigned_at: null } as Row;
}

describe("queue grouping", () => {
  it("uses Moscow dates and keeps the server's order within each group", () => {
    const now = new Date("2026-10-26T04:00:00Z");
    const rows = [
      row("first", "2026-10-25T21:05:00Z"),
      row("second", "2026-10-25T21:00:00Z"),
      row("third", "2026-10-25T20:59:00Z"),
    ];
    const groups = groupQueue(rows, "-created_at", now);
    expect(groups.map((group) => group.label)).toEqual([
      "Сегодня, 26 октября",
      "Вчера, 25 октября",
    ]);
    expect(
      groups.flatMap((group) => group.rows.map((item) => item.id)),
    ).toEqual(["first", "second", "third"]);
  });

  it("does not reorder an amount-sorted page to make date groups", () => {
    const rows = [
      row("older", "2026-10-24T09:00:00Z"),
      row("newer", "2026-10-26T09:00:00Z"),
    ];
    expect(groupQueue(rows, "-amount")).toEqual([
      { key: "ordered", label: "", rows },
    ]);
  });
});

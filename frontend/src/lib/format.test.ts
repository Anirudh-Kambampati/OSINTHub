import { describe, expect, it } from "vitest";
import { formatConfidence, safeHref } from "./format";
import { levelOf } from "./meta";

describe("formatConfidence", () => {
  it("avoids false precision for weak evidence", () => {
    expect(formatConfidence(0.37)).toBe("~35%");
    expect(formatConfidence(0.91)).toBe("91%");
    expect(formatConfidence(null)).toBe("—");
  });
});

describe("levelOf", () => {
  it("maps scores to the documented bands", () => {
    expect(levelOf(0.1)).toBe("low");
    expect(levelOf(0.3)).toBe("medium");
    expect(levelOf(0.6)).toBe("high");
    expect(levelOf(0.85)).toBe("very_high");
  });
});

describe("safeHref", () => {
  it("only allows http(s) links", () => {
    expect(safeHref("javascript:alert(1)")).toBeUndefined();
    expect(safeHref("data:text/html,hi")).toBeUndefined();
    expect(safeHref("example.com")).toBe("https://example.com/");
    expect(safeHref("http://example.com/a")).toBe("http://example.com/a");
  });
});

import { describe, expect, it } from "vitest";

import { classifySearchErrorCode } from "./failure";

describe("classifySearchErrorCode", () => {
  it("handles structured server errors without throwing", () => {
    expect(classifySearchErrorCode([{ message: "invalid request" }])).toBe("server_error");
  });
});

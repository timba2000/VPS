import { describe, expect, it } from "vitest";

import { loadUserComments as buggy } from "../src/buggy.js";
import { loadUserComments as fixed } from "../src/fixed.js";
import type { Source } from "../src/types.js";

function makeSource(): Source {
  return {
    async fetchUsers() {
      return [
        { id: 1, name: "Alice" },
        { id: 2, name: "Bob" },
      ];
    },
    async fetchCommentsFor(userId: number) {
      // Simulate a real async boundary so the bug is observable.
      await new Promise((r) => setTimeout(r, 5));
      return [{ userId, text: `comment-${userId}` }];
    },
  };
}

describe("loadUserComments", () => {
  it("buggy version returns an empty result (the bug)", async () => {
    const out = await buggy(makeSource());
    expect(out).toEqual({});
  });

  it("fixed version returns comments for every user", async () => {
    const out = await fixed(makeSource());
    expect(out).toEqual({
      1: [{ userId: 1, text: "comment-1" }],
      2: [{ userId: 2, text: "comment-2" }],
    });
  });
});

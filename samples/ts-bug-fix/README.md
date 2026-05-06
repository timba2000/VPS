# ts-bug-fix — async forEach pitfall

A small worked example of the kind of bug I get hired to fix on Fiverr: code that *looks right*, passes a casual eye test, but silently misbehaves when async is involved.

## The bug

```ts
async function loadUserComments(source) {
  const users = await source.fetchUsers();
  const result = {};
  users.forEach(async (user) => {
    result[user.id] = await source.fetchCommentsFor(user.id);
  });
  return result;  // returns {} — the async callbacks haven't resolved yet
}
```

`Array.prototype.forEach` does not await its callback. The outer function returns immediately; the inner `await`s resolve after the caller has already moved on. Result: an empty `{}` (or partial state, depending on timing).

This is a classic real-world bug: tests written against a synchronous mock pass because everything happens before the next microtask, but the same code returns empty objects in production where the real fetches actually take time.

## The fix

```ts
async function loadUserComments(source) {
  const users = await source.fetchUsers();
  const entries = await Promise.all(
    users.map(async (user) => [user.id, await source.fetchCommentsFor(user.id)]),
  );
  return Object.fromEntries(entries);
}
```

`Promise.all(map(...))` awaits all the inner promises before the function resolves. As a bonus, the fetches now run in parallel rather than sequentially.

## Run it

```bash
npm install
npm test
```

Two tests run against the same mock source:

- `buggy.ts` — asserts the broken behavior (`{}`) so you can see the bug is real
- `fixed.ts` — asserts the correct output

```
✓ buggy version returns an empty result (the bug)
✓ fixed version returns comments for every user
```

## How I'd deliver this on a real engagement

1. A failing test that reproduces the bug with the customer's actual data shape.
2. The minimal diff to fix it.
3. A short write-up (this file) explaining the why, so the same bug doesn't reappear next month in a different file.

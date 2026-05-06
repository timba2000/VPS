import type { Comment, Source } from "./types.js";

export async function loadUserComments(
  source: Source,
): Promise<Record<number, Comment[]>> {
  const users = await source.fetchUsers();
  const result: Record<number, Comment[]> = {};

  // BUG: forEach does not await async callbacks. The function returns
  // before the inner fetches resolve, so result is observed empty.
  users.forEach(async (user) => {
    result[user.id] = await source.fetchCommentsFor(user.id);
  });

  return result;
}

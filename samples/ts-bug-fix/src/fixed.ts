import type { Comment, Source } from "./types.js";

export async function loadUserComments(
  source: Source,
): Promise<Record<number, Comment[]>> {
  const users = await source.fetchUsers();
  const entries = await Promise.all(
    users.map(
      async (user) => [user.id, await source.fetchCommentsFor(user.id)] as const,
    ),
  );
  return Object.fromEntries(entries);
}

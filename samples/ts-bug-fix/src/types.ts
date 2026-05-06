export type User = { id: number; name: string };
export type Comment = { userId: number; text: string };

export type Source = {
  fetchUsers(): Promise<User[]>;
  fetchCommentsFor(userId: number): Promise<Comment[]>;
};

import { eq, sql } from "drizzle-orm";
import type { Executor } from "../client.ts";
import { user } from "../schema/index.ts";

export type UserRole = "user" | "admin";

/**
 * Sets a user's role by email (case-insensitive). Only the operator CLI calls this; no server
 * function can change a role. Returns false when no account has that address.
 */
export async function setUserRole(ex: Executor, email: string, role: UserRole): Promise<boolean> {
  const rows = await ex
    .update(user)
    .set({ role })
    .where(eq(sql`lower(${user.email})`, email.trim().toLowerCase()))
    .returning({ id: user.id });
  return rows.length > 0;
}

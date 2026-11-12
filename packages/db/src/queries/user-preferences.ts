import { eq } from "drizzle-orm";
import type { Executor } from "../client.ts";
import { userPreference } from "../schema/index.ts";

export type UserPreferences = Omit<typeof userPreference.$inferSelect, "updatedAt">;
export type UserPreferenceChanges = Partial<Omit<UserPreferences, "userId">>;

/** A user's preferences. Users who never changed one get the column defaults. */
export async function getUserPreferences(ex: Executor, userId: string): Promise<UserPreferences> {
  const [row] = await ex.select().from(userPreference).where(eq(userPreference.userId, userId));
  if (row) {
    const { updatedAt: _updatedAt, ...preferences } = row;
    return preferences;
  }
  return { userId, analysisCompleteEmail: true, soundEnabled: false, units: "metric" };
}

export async function updateUserPreferences(
  ex: Executor,
  userId: string,
  changes: UserPreferenceChanges,
): Promise<UserPreferences> {
  await ex
    .insert(userPreference)
    .values({ userId, ...changes })
    .onConflictDoUpdate({ target: userPreference.userId, set: changes });
  return getUserPreferences(ex, userId);
}

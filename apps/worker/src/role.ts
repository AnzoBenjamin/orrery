/**
 * Operator CLI: `make admin email=<address>` grants the admin role (the operator page);
 * `revoke=1` takes it away. Roles change only here, never through the web app.
 */
import { loadMigrateEnv } from "@orrery/config/migrate";
import { createDb, setUserRole } from "@orrery/db";

const [action, email] = process.argv.slice(2);
if ((action !== "grant" && action !== "revoke") || !email) {
  process.stderr.write("usage: role grant|revoke <email>\n");
  process.exit(2);
}

const env = loadMigrateEnv();
const handle = createDb({
  connectionString: env.DATABASE_URL,
  max: 1,
  applicationName: "orrery-role",
});
try {
  const changed = await setUserRole(handle.db, email, action === "grant" ? "admin" : "user");
  if (!changed) {
    process.stderr.write(`role: no account uses ${email}\n`);
    process.exitCode = 1;
  } else {
    process.stdout.write(`role: ${email} is now ${action === "grant" ? "an admin" : "a user"}\n`);
  }
} finally {
  await handle.close();
}

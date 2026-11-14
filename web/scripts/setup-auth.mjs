// Crée les tables Better Auth et le compte administrateur (juges). La démo publique ne demande pas de compte.
// Usage : node --env-file=.env.local scripts/setup-auth.mjs   (idempotent : ne recrée pas un compte existant)
import { betterAuth } from "better-auth";
import { admin } from "better-auth/plugins";
import { getMigrations } from "better-auth/db/migration";
import { Pool } from "pg";

const pool = new Pool({ connectionString: process.env.AUTH_DATABASE_URL });
const options = {
  database: pool,
  secret: process.env.BETTER_AUTH_SECRET,
  baseURL: process.env.BETTER_AUTH_URL,
  emailAndPassword: { enabled: true, disableSignUp: true, minPasswordLength: 10 },
  plugins: [admin({ defaultRole: "demo", adminRoles: ["admin"] })],
};
const { toBeCreated, toBeAdded, runMigrations } = await getMigrations(options);
console.log(`migrations: ${toBeCreated.length} table(s) to create, ${toBeAdded.length} to alter`);
await runMigrations();

const auth = betterAuth(options);
const accounts = [
  { email: process.env.ADMIN_EMAIL, password: process.env.ADMIN_PASSWORD, name: "Hostinger judges", role: "admin" },
];
for (const a of accounts) {
  if (!a.email || !a.password) { console.log("skip: missing email/password in env"); continue; }
  const { rows } = await pool.query('select id, role from "user" where email = $1', [a.email.toLowerCase()]);
  if (rows.length) { console.log(`exists: ${a.email} (${rows[0].role})`); continue; }
  const r = await auth.api.createUser({ body: a });
  console.log(`created: ${r.user.email} (${r.user.role})`);
}
await pool.end();

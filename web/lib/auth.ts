import { betterAuth } from "better-auth";
import { admin } from "better-auth/plugins";
import { nextCookies } from "better-auth/next-js";
import { Pool } from "pg";

/** Authentification (Better Auth). Comptes créés par l'administrateur uniquement (pas d'inscription publique).
 *  Seuls les administrateurs se connectent (accès complet, clés API). Les visiteurs non connectés voient la démo
 *  publique : lecture seule des données publiées (cf. /backend).
 *  Sessions en base : chaque connexion a sa propre session, plusieurs personnes peuvent être connectées
 *  en même temps, y compris sur le même compte. */
export const auth = betterAuth({
  database: new Pool({ connectionString: process.env.AUTH_DATABASE_URL, max: 10 }),
  secret: process.env.BETTER_AUTH_SECRET,
  baseURL: process.env.BETTER_AUTH_URL,
  emailAndPassword: { enabled: true, disableSignUp: true, minPasswordLength: 10 },
  session: { expiresIn: 60 * 60 * 24 * 7, updateAge: 60 * 60 * 24, cookieCache: { enabled: true, maxAge: 60 } },
  // Les juges peuvent se connecter ensemble depuis le même réseau (même IP) : la limite par défaut sur la connexion
  // (~3 essais / 10 s) les bloquerait. 30 essais par minute et par IP freinent toujours le brute force.
  rateLimit: { enabled: true, window: 60, max: 300, customRules: { "/sign-in/email": { window: 60, max: 30 } } },
  plugins: [admin({ defaultRole: "demo", adminRoles: ["admin"] }), nextCookies()],
});

export type Role = "admin" | "demo";
export const roleOf = (u: { role?: string | null } | null | undefined): Role => (u?.role === "admin" ? "admin" : "demo");

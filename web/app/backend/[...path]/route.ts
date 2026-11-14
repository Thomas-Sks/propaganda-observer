import { auth, roleOf } from "@/lib/auth";

/** Backend-for-frontend : le navigateur n'appelle JAMAIS FastAPI directement.
 *  1. administrateur connecté (Better Auth) : accès complet ;
 *  2. visiteur sans session = démo publique : le rôle « demo » est transmis à FastAPI, qui ne sert alors QUE
 *     l'instantané publié (aucun calcul, aucun appel externe ni payant) ; ici on refuse déjà toute écriture et le
 *     flux temps réel ;
 *  3. transmission avec le jeton interne ; le flux SSE (admin) est relayé tel quel. */
const BACKEND = process.env.BACKEND_URL ?? "http://localhost:8010";

function demoAllowed(method: string, path: string) {
  if (path.startsWith("/api/stream/") || path.endsWith("/publish")) return false;
  if (method === "GET") return true;
  return method === "POST" && /^\/api\/events\/[^/]+\/stories\/[^/]+\/investigate$/.test(path);  // relecture d'une enquête publiée
}

async function handle(req: Request, { params }: { params: Promise<{ path: string[] }> }) {
  // Vérifié en base à chaque appel (pas de cache cookie) : une session révoquée ne passe plus jamais
  const session = await auth.api.getSession({ headers: req.headers, query: { disableCookieCache: true } });
  const role = session ? roleOf(session.user) : "demo";  // pas de session : démo publique en lecture seule
  const path = "/" + (await params).path.join("/");
  if (role === "demo" && !demoAllowed(req.method, path)) {
    return Response.json({ detail: "The public demo is read-only: it shows published data only." }, { status: 403 });
  }
  const target = new URL(BACKEND + path);
  new URL(req.url).searchParams.forEach((v, k) => target.searchParams.set(k, v));
  const upstream = await fetch(target, {
    method: req.method,
    headers: {
      "content-type": req.headers.get("content-type") ?? "application/json",
      accept: req.headers.get("accept") ?? "*/*",
      "x-internal-token": process.env.BACKEND_TOKEN ?? "",
      "x-viewer-role": role,
    },
    body: req.method === "GET" || req.method === "HEAD" ? undefined : await req.text(),
    signal: req.signal,
    cache: "no-store",
  });
  const headers = new Headers({ "content-type": upstream.headers.get("content-type") ?? "application/json" });
  if (headers.get("content-type")?.includes("text/event-stream")) {
    headers.set("cache-control", "no-cache, no-transform");
    headers.set("x-accel-buffering", "no");  // pas de mise en tampon derrière un reverse proxy (Hostinger)
  }
  return new Response(upstream.body, { status: upstream.status, headers });
}

export { handle as GET, handle as POST };

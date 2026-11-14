"use client";
import { createAuthClient } from "better-auth/react";
import { adminClient } from "better-auth/client/plugins";

export const authClient = createAuthClient({ plugins: [adminClient()] });
export const { useSession, signIn, signOut } = authClient;
export const isAdmin = (u: { role?: string | null } | null | undefined) => u?.role === "admin";

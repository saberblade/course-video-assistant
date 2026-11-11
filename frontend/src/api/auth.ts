import { http } from "./http";
import { acceptSession, clearSession, sessionState, type AuthSession, type User } from "@/stores/session";

let restoring: Promise<void> | undefined;
export function restoreSession(): Promise<void> {
  if (sessionState.checked.value) return Promise.resolve();
  if (restoring) return restoring;
  const revision = sessionState.revision.value;
  restoring = http.get<AuthSession>("/auth/me", { timeout: 8_000, headers: { "Cache-Control": "no-cache" } })
    .then(({ data }) => { if (revision === sessionState.revision.value) acceptSession(data); })
    .catch(error => {
      if (revision !== sessionState.revision.value) return;
      if (error.response?.status === 401) clearSession("");
      else throw error;
    })
    .finally(() => { restoring = undefined; });
  return restoring;
}

export async function login(username: string, password: string) {
  const { data } = await http.post<AuthSession>("/auth/login", { username: username.trim(), password });
  acceptSession(data, true);
}
export async function register(username: string, password: string, displayName: string) {
  await http.post<User>("/auth/register", { username: username.trim(), password, display_name: displayName.trim() });
}
export async function logout() {
  await http.post("/auth/logout");
  clearSession("logout", true);
}

// Only allow in-app business routes after sign-in, never a supplied external URL.
export function loginDestination(value: unknown): string {
  if (typeof value !== "string" || !value.startsWith("/") || value.startsWith("//") || value.includes("\\")) return "/screen";
  try {
    const parsed = new URL(value, window.location.origin);
    if (parsed.origin !== window.location.origin || !/^\/(screen\/?|videos\/[^/.]+\/?)$/.test(parsed.pathname)) return "/screen";
    return parsed.pathname + parsed.search + parsed.hash;
  } catch { return "/screen"; }
}

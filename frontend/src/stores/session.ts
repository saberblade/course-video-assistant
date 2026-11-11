import { readonly, ref } from "vue";

export interface User {
  id: string;
  username: string;
  display_name: string;
}
export interface AuthSession { user: User; csrf_token: string }

const user = ref<User | null>(null);
const revision = ref(0);
const checked = ref(false);
const reason = ref<"" | "expired" | "changed" | "logout">("");
let csrf = "";
let requests = new AbortController();
const channel = typeof BroadcastChannel === "undefined" ? undefined : new BroadcastChannel("course-review:session");

function rotate() {
  requests.abort();
  requests = new AbortController();
  revision.value++;
}

export function acceptSession(session: AuthSession, announce = false) {
  if (user.value?.id !== session.user.id || csrf !== session.csrf_token) rotate();
  csrf = session.csrf_token;
  user.value = session.user;
  checked.value = true;
  reason.value = "";
  if (announce) channel?.postMessage("changed");
}

export function clearSession(why: typeof reason.value, announce = false) {
  csrf = "";
  user.value = null;
  checked.value = why !== "changed";
  reason.value = why;
  rotate();
  if (announce) channel?.postMessage("changed");
}

if (channel) channel.onmessage = () => clearSession("changed");
if (import.meta.hot) import.meta.hot.dispose(() => channel?.close());

export const sessionState = {
  user: readonly(user), revision: readonly(revision), checked: readonly(checked), reason: readonly(reason),
};
export const sessionToken = () => csrf;
export const sessionSignal = () => requests.signal;

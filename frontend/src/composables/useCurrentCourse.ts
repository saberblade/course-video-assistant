import { ref, watch } from "vue";
import { sessionState } from "@/stores/session";

// UI context only; the server still validates ownership on every request.
// Shared across the workspaces, never used to filter the full course library.
const selectedId = ref("");
const stop = watch(sessionState.revision, () => { selectedId.value = ""; }, { flush: "sync" });
if (import.meta.hot) import.meta.hot.dispose(stop);

export function useCurrentCourse() {
  return { selectedId };
}

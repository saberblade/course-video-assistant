import { createRouter, createWebHistory } from "vue-router";
import HomeView from "@/views/HomeView.vue";
import VideoDetailView from "@/views/VideoDetailView.vue";
import { watch } from "vue";
import { restoreSession, loginDestination } from "@/api/auth";
import { isMock } from "@/api/http";
import { sessionState } from "@/stores/session";

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/", name: "home", component: HomeView },
    { path: "/login", name: "login", component: () => import("@/views/LoginView.vue") },
    { path: "/videos/:id", name: "video-detail", component: VideoDetailView, meta: { requiresAuth: true } },
    {
      path: "/screen",
      name: "screen",
      component: () => import("@/views/ScreenView.vue"),
      meta: { requiresAuth: true },
    },
    { path: "/:pathMatch(.*)*", redirect: "/" },
  ],
  scrollBehavior: () => ({ top: 0 }),
});

router.beforeEach(async to => {
  if (isMock) return true;
  if (to.name === "home") { void restoreSession().catch(() => undefined); return true; }
  try { await restoreSession(); }
  catch {
    if (to.meta.requiresAuth) return { name: "login", query: { redirect: to.fullPath, reason: "unavailable" } };
  }
  if (to.meta.requiresAuth && !sessionState.user.value) {
    return { name: "login", query: { redirect: to.fullPath, ...(sessionState.reason.value ? { reason: sessionState.reason.value } : {}) } };
  }
  if (to.name === "login" && sessionState.user.value) return loginDestination(to.query.redirect);
  return true;
});

watch(sessionState.revision, () => {
  const route = router.currentRoute.value;
  if (!isMock && !sessionState.user.value && route.meta.requiresAuth) {
    void router.replace({ name: "login", query: { redirect: route.fullPath, reason: sessionState.reason.value || "expired" } });
  }
});

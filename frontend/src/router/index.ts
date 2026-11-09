import { createRouter, createWebHistory } from "vue-router";
import HomeView from "@/views/HomeView.vue";
import VideoDetailView from "@/views/VideoDetailView.vue";

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/", name: "home", component: HomeView },
    { path: "/videos/:id", name: "video-detail", component: VideoDetailView },
    {
      path: "/screen",
      name: "screen",
      component: () => import("@/views/ScreenView.vue"),
    },
    { path: "/:pathMatch(.*)*", redirect: "/" },
  ],
  scrollBehavior: () => ({ top: 0 }),
});

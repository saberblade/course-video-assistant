<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import ScreenTopBar from "@/components/screen/ScreenTopBar.vue";
import ScreenLibrary from "@/components/screen/ScreenLibrary.vue";
import ReviewWorkspace from "@/components/screen/ReviewWorkspace.vue";
import { api } from "@/api";
import { toApiError } from "@/api/http";
import type { Video } from "@/types";
import { useCurrentCourse } from "@/composables/useCurrentCourse";
import "@/styles/screen.css";

const router = useRouter();
const route = useRoute();
const { selectedId } = useCurrentCourse();
watch(() => route.query.video, id => {
  if (typeof id === "string" && id) selectedId.value = id;
}, { immediate: true });
const view = computed<"map" | "library" | "analysis" | "weak">(() => {
  const key = route.query.view;
  return key === "library" || key === "analysis" || key === "weak" ? key : "map";
});
const videos = ref<Video[]>([]);
const recentVideos = ref<Video[]>([]);
const page = ref(1);
const total = ref(0);
const pageSize = 50;
const loadingVideos = ref(true);
const loadError = ref("");
const readyVideo = computed(() => recentVideos.value.find(video => video.status === "ready") ?? null);
let listRequest = 0;
let disposed = false;
const reviewLayer = ref<HTMLElement>();
watch(view, () => reviewLayer.value?.scrollTo({ top: 0 }), { flush: "post" });

function onNav(key: string) {
  void router.push({ name: "screen", query: { ...(key === "map" ? {} : { view: key }), ...(selectedId.value ? { video: selectedId.value } : {}) } });
}
function openVideo(video: Video) {
  if (video.status === "ready") selectedId.value = video.id;
  void router.push({ name: "video-detail", params: { id: video.id }, query: { from: "screen", view: "library" } });
}
async function loadVideos(pageNumber = page.value) {
  const request = ++listRequest;
  loadingVideos.value = true;
  loadError.value = "";
  try {
    const res = await api.listVideos(pageSize, (pageNumber - 1) * pageSize);
    if (disposed || request !== listRequest) return;
    const lastPage = Math.max(1, Math.ceil(res.total / pageSize));
    if (pageNumber > lastPage) { await loadVideos(lastPage); return; }
    page.value = pageNumber;
    total.value = res.total;
    videos.value = res.items;
    if (pageNumber === 1) recentVideos.value = res.items;
  } catch (error) {
    if (request === listRequest && !disposed) loadError.value = toApiError(error).message;
  } finally {
    if (request === listRequest && !disposed) loadingVideos.value = false;
  }
}
onMounted(loadVideos);
onBeforeUnmount(() => { disposed = true; listRequest++; });
</script>

<template>
  <div class="scr-shell">
    <ScreenTopBar :active="view" @nav="onNav" @exit="router.push('/')" />
    <main class="scr-stage">
      <div v-show="view === 'library'" class="workspace-layer">
        <ScreenLibrary :videos="videos" :loading="loadingVideos" :load-error="loadError" :total="total" :page="page" :page-size="pageSize" :ready-video="readyVideo" @refresh="loadVideos()" @page="loadVideos" @open="openVideo" />
      </div>
      <div v-if="view !== 'library'" ref="reviewLayer" class="workspace-layer" :class="{ 'workspace-layer--map': view === 'map' }">
        <ReviewWorkspace :view="view" @nav="onNav" />
      </div>
      <footer v-if="view === 'library'" class="library-status"><span>课程列表</span><span v-if="!loadingVideos && !loadError">共 {{ total }} 门课程</span></footer>
    </main>
  </div>
</template>

<style scoped>
.workspace-layer { position: absolute; inset: 0; overflow-y: auto; overflow-x: hidden; padding-bottom: 34px; scrollbar-width: thin; }
.workspace-layer--map { padding-bottom: 0; }
.library-status { position: absolute; left: 0; right: 0; bottom: 0; z-index: 6; display: flex; justify-content: space-between; align-items: center; height: 30px; padding: 0 26px; border-top: 1px solid var(--scr-line); background: rgba(255,255,255,.94); color: var(--scr-text-faint); font-size: 10.5px; pointer-events: none; }
@media (max-width: 700px) { .workspace-layer { padding-bottom: 0; }.library-status { display: none; } }
</style>

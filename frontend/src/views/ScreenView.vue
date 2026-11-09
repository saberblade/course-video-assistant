<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import ScreenTopBar from "@/components/screen/ScreenTopBar.vue";
import ScreenLegend from "@/components/screen/ScreenLegend.vue";
import ScreenSearch from "@/components/screen/ScreenSearch.vue";
import ScreenDetail from "@/components/screen/ScreenDetail.vue";
import ScreenLibrary from "@/components/screen/ScreenLibrary.vue";
import ScreenAnalysis from "@/components/screen/ScreenAnalysis.vue";
import KnowledgeMap from "@/components/screen/KnowledgeMap.vue";
import {
  STATUS_META,
  knowledgeLinks,
  knowledgeModules,
  knowledgeNodes,
  statusCounts,
  type KnowledgeNode,
  type KnowledgeStatus,
} from "@/data/knowledgeMap";
import { api, isMock } from "@/api";
import { toApiError } from "@/api/http";
import { KNOWLEDGE_MAP_SAMPLE_ID } from "@/api/mock";
import type { Video } from "@/types";
import { formatDuration } from "@/utils/format";
import "@/styles/screen.css";
import "@/styles/screen-map.css";

type ViewKey = "map" | "library" | "analysis" | "weak";

const router = useRouter();
const route = useRoute();

const view = computed<ViewKey>(() => {
  const key = route.query.view;
  return key === "library" || key === "analysis" || key === "weak" ? key : "map";
});
const activeId = ref("");
const detailOpen = ref(false);
const keyword = ref("");
const hidden = ref<KnowledgeStatus[]>([]);
const scale = ref(1);
const toast = ref("");
const mapRef = ref<InstanceType<typeof KnowledgeMap>>();
const shell = ref<HTMLElement>();
const analysisLayer = ref<HTMLElement>();

const videos = ref<Video[]>([]);
const recentVideos = ref<Video[]>([]);
const page = ref(1);
const total = ref(0);
const pageSize = 50;
const loadingVideos = ref(true);
const loadError = ref("");
const readyVideo = computed(() => recentVideos.value.find((video) => video.status === "ready") ?? null);
const sampleVideo = computed(() =>
  isMock ? recentVideos.value.find((video) => video.id === KNOWLEDGE_MAP_SAMPLE_ID && video.status === "ready") : undefined,
);

let toastTimer = 0;
let listRequest = 0;

const activeDetail = computed(() => view.value === "map" && detailOpen.value);

const matched = computed(() => {
  const key = keyword.value.trim();
  if (!key) return knowledgeNodes.length;
  return knowledgeNodes.filter((node) => node.name.includes(key) || node.chapter.includes(key)).length;
});

const mastery = computed(() =>
  Math.round(((statusCounts.ok + statusCounts.warn * 0.5) / knowledgeNodes.length) * 100),
);

const stats = computed(() => [
  { label: "演示课程", value: "1" },
  { label: "示例知识点", value: String(knowledgeNodes.length) },
  { label: "示例章节", value: String(new Set(knowledgeNodes.map((node) => node.chapter)).size) },
  { label: "样例时长", value: sampleVideo.value ? formatDuration(sampleVideo.value.duration_sec) : "—" },
]);

const activeNode = computed(() => knowledgeNodes.find((node) => node.id === activeId.value) ?? null);

const counts = computed(() => statusCounts);

function showToast(text: string) {
  toast.value = text;
  window.clearTimeout(toastTimer);
  toastTimer = window.setTimeout(() => (toast.value = ""), 2200);
}

function toggleStatus(status: KnowledgeStatus) {
  hidden.value = hidden.value.includes(status)
    ? hidden.value.filter((item) => item !== status)
    : [...hidden.value, status];
  const meta = STATUS_META[status];
  showToast(hidden.value.includes(status) ? `已隐藏「${meta.label}」知识点` : `已显示「${meta.label}」知识点`);
}

function selectNode(node: KnowledgeNode) {
  activeId.value = node.id;
  detailOpen.value = true;
}

function pickNode(node: KnowledgeNode) {
  selectNode(node);
}

function closeDetail() {
  detailOpen.value = false;
}

function openSample(node?: KnowledgeNode) {
  if (!sampleVideo.value) return;
  const query: Record<string, string> = { from: "screen" };
  if (node) query.t = String(node.time);
  router.push({ name: "video-detail", params: { id: sampleVideo.value.id }, query });
}

function openVideo(video: Video) {
  closeDetail();
  router.push({ name: "video-detail", params: { id: video.id }, query: { from: "screen", view: "library" } });
}

function onNav(key: string) {
  router.push({ name: "screen", query: key === "map" ? {} : { view: key } });
}

function jumpToNode(node: KnowledgeNode) {
  onNav("map");
  selectNode(node);
}

function exitScreen() {
  router.push("/");
}

async function toggleFullscreen() {
  try {
    if (document.fullscreenElement) await document.exitFullscreen();
    else await shell.value?.requestFullscreen();
  } catch {
    showToast("当前浏览器不允许进入全屏");
  }
}

function onScale(value: number) {
  scale.value = value;
}

async function loadVideos(pageNumber = page.value) {
  const request = ++listRequest;
  loadingVideos.value = true;
  loadError.value = "";
  try {
    const res = await api.listVideos(pageSize, (pageNumber - 1) * pageSize);
    if (request !== listRequest) return;
    const lastPage = Math.max(1, Math.ceil(res.total / pageSize));
    if (pageNumber > lastPage) {
      await loadVideos(lastPage);
      return;
    }
    page.value = pageNumber;
    total.value = res.total;
    videos.value = res.items;
    if (pageNumber === 1) recentVideos.value = res.items;
  } catch (error) {
    if (request === listRequest) loadError.value = toApiError(error).message;
  } finally {
    if (request === listRequest) loadingVideos.value = false;
  }
}

onMounted(loadVideos);

watch(view, (key) => {
  if (key !== "map") closeDetail();
  if (key === "analysis" || key === "weak") analysisLayer.value?.scrollTo(0, 0);
}, { flush: "post" });

onBeforeUnmount(() => window.clearTimeout(toastTimer));
</script>

<template>
  <div ref="shell" class="scr-shell" :class="{ 'has-detail': activeDetail }">
    <ScreenTopBar :active="view" @nav="onNav" @exit="exitScreen" />

    <main class="scr-stage">
      <!-- 知识地图 -->
      <div v-show="view === 'map'" class="scr-layer">
        <div class="scr-headline">
          <div class="scr-headline__row">
            <span class="scr-headline__deco" />
            <h1>分类模型评估 · 示例知识地图</h1>
            <span class="scr-headline__deco scr-headline__deco--right" />
          </div>
          <p class="scr-headline__sub">演示知识点与掌握状态 · 数据为预设教学示例</p>
        </div>

        <ScreenLegend
          :counts="counts"
          :hidden="hidden"
          :stats="stats"
          @toggle="toggleStatus"
        />

        <ScreenSearch
          :nodes="knowledgeNodes"
          :matched="matched"
          :keyword="keyword"
          @change="keyword = $event"
          @pick="pickNode"
        />

        <KnowledgeMap
          ref="mapRef"
          :nodes="knowledgeNodes"
          :modules="knowledgeModules"
          :links="knowledgeLinks"
          :active-id="activeId"
          :keyword="keyword"
          :hidden="hidden"
          @select="selectNode"
          @scale="onScale"
        />

        <div class="scr-ctrl">
          <button type="button" class="scr-ctrl__btn" aria-label="放大" @click="mapRef?.zoomIn()">+</button>
          <button type="button" class="scr-ctrl__btn" aria-label="缩小" @click="mapRef?.zoomOut()">−</button>
          <button type="button" class="scr-ctrl__btn" aria-label="复位" @click="mapRef?.reset()">⌂</button>
          <span class="scr-ctrl__scale">{{ Math.round(scale * 100) }}%</span>
        </div>

        <button type="button" class="scr-fab" aria-label="全屏" @click="toggleFullscreen">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5" stroke-linecap="round" />
          </svg>
        </button>

        <div class="scr-dock">
          <div class="scr-dock__meta">
            <span class="scr-dock__label">示例掌握度</span>
            <span class="scr-dock__title">{{ sampleVideo ? "分类模型评估 · 演示课程" : "分类模型评估 · 示例地图" }}</span>
          </div>
          <div class="scr-dock__bar"><i :style="{ width: `${mastery}%` }" /></div>
          <span class="scr-dock__pct">{{ mastery }}%</span>
          <button v-if="sampleVideo" type="button" class="scr-dock__go" @click="openSample(activeNode ?? undefined)">
            打开演示课程
          </button>
        </div>

        <ScreenDetail
          :node="activeNode"
          :open="detailOpen"
          :sample-available="Boolean(sampleVideo)"
          @close="closeDetail"
          @go="openSample"
        />
      </div>

      <!-- 我的课程 -->
      <div v-show="view === 'library'" class="scr-layer scr-layer--scroll">
        <ScreenLibrary
          :videos="videos"
          :loading="loadingVideos"
          :load-error="loadError"
          :total="total"
          :page="page"
          :page-size="pageSize"
          :ready-video="readyVideo"
          @refresh="loadVideos()"
          @page="loadVideos"
          @open="openVideo"
        />
      </div>

      <!-- 学习分析 / 薄弱预警 -->
      <div v-show="view === 'analysis' || view === 'weak'" ref="analysisLayer" class="scr-layer scr-layer--scroll">
        <ScreenAnalysis
          :weak-only="view === 'weak'"
          @goto="jumpToNode"
          @open-map="onNav('map')"
          @open-weak="onNav('weak')"
        />
      </div>

      <transition name="scr-fade">
        <div v-if="toast" class="scr-toast">{{ toast }}</div>
      </transition>

      <footer v-if="view !== 'map'" class="scr-statusbar">
        <span v-if="view === 'library'">课程列表 · {{ isMock ? "演示数据" : "真实接口" }}</span>
        <span v-else>{{ view === "weak" ? "薄弱预警" : "学习分析" }} · 预设教学示例</span>
        <span v-if="view === 'analysis'" class="scr-statusbar__mid">
          示例知识点 <b>{{ knowledgeNodes.length }}</b>
          <i />
          已掌握 <b>{{ counts.ok }}</b>
          <i />
          待复习 <b>{{ counts.warn }}</b>
          <i />
          薄弱 <b>{{ counts.bad }}</b>
        </span>
        <span v-if="view === 'analysis'">示例掌握度 {{ mastery }}%</span>
        <span v-else-if="view === 'library' && !loadingVideos && !loadError">共 {{ total }} 门课程</span>
      </footer>
    </main>
  </div>
</template>

<style scoped>
.scr-layer {
  position: absolute;
  inset: 0;
}

.scr-layer--scroll {
  overflow-y: auto;
  overflow-x: hidden;
  padding-bottom: 34px;
  scrollbar-width: thin;
}

.scr-statusbar {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  z-index: 6;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
  height: 30px;
  padding: 0 26px;
  border-top: 1px solid var(--scr-line);
  background: rgba(255, 255, 255, 0.92);
  color: var(--scr-text-faint);
  font-size: 10.5px;
  letter-spacing: 0.3px;
  pointer-events: none;
  backdrop-filter: blur(6px);
}

.scr-statusbar__mid {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.scr-statusbar__mid i {
  width: 2px;
  height: 2px;
  border-radius: 50%;
  background: #bac9cb;
}

.scr-statusbar__mid b {
  color: var(--scr-text-dim);
  font-family: "Bahnschrift", Consolas, monospace;
  font-size: 11px;
  font-weight: 500;
}

@media (max-width: 700px) {
  .scr-statusbar {
    display: none;
  }
  .scr-layer--scroll {
    padding-bottom: 0;
  }
}

.scr-toast {
  position: absolute;
  left: 50%;
  bottom: 92px;
  z-index: 10;
  transform: translateX(-50%);
  padding: 8px 18px;
  border: 1px solid var(--scr-line);
  border-radius: 30px;
  background: rgba(255, 255, 255, 0.96);
  color: var(--scr-text);
  font-size: 12.5px;
  white-space: nowrap;
  box-shadow: 0 10px 26px rgba(28, 62, 68, 0.13);
}

.scr-fade-enter-active,
.scr-fade-leave-active {
  transition: opacity 0.24s ease, transform 0.24s ease;
}

.scr-fade-enter-from,
.scr-fade-leave-to {
  opacity: 0;
  transform: translate(-50%, 6px);
}
</style>

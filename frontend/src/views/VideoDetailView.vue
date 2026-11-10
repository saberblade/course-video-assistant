<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ArrowLeft, Clock, Delete, InfoFilled, Refresh, VideoCamera, WarningFilled } from "@element-plus/icons-vue";
import { ElMessage, ElMessageBox } from "element-plus";
import ChapterList from "@/components/ChapterList.vue";
import ProcessingPanel from "@/components/ProcessingPanel.vue";
import QuestionPanel from "@/components/QuestionPanel.vue";
import ScreenTopBar from "@/components/screen/ScreenTopBar.vue";
import StatusBadge from "@/components/StatusBadge.vue";
import TranscriptPanel from "@/components/TranscriptPanel.vue";
import VideoPlayer from "@/components/VideoPlayer.vue";
import { api, isMock } from "@/api";
import { toApiError } from "@/api/http";
import { mockApi } from "@/api/mock";
import type { Chapter, TranscriptSegment, Video, VideoStatus } from "@/types";
import { formatDate, formatDuration } from "@/utils/format";
import "@/styles/screen.css";

const route = useRoute();
const router = useRouter();
const videoId = computed(() => String(route.params.id));
const video = ref<Video | null>(null);
const segments = ref<TranscriptSegment[]>([]);
const chapters = ref<Chapter[]>([]);
const initialLoading = ref(true);
const initialError = ref("");
const contentError = ref("");
const contentLoading = ref(false);
const contentLoaded = ref(false);
const refreshing = ref(false);
const connectionError = ref("");
const deleting = ref(false);
const retrying = ref(false);
const playerRef = ref<InstanceType<typeof VideoPlayer>>();
const playerSection = ref<HTMLElement>();
const scrollArea = ref<HTMLElement>();
const activePanel = ref(route.query.panel === "question" ? "question" : "chapters");
const timeQuery = route.query.t;
const startAt = typeof timeQuery === "string" && timeQuery.trim() ? Number(timeQuery) : NaN;
let pendingStartAt = Number.isFinite(startAt) && startAt >= 0 ? startAt : null;
let pollTimer: number | undefined;
let fetchInFlight = false;
let disposed = false;

const backView = computed(() => {
  const view = route.query.view;
  if (view === "library" || view === "analysis" || view === "weak") return view;
  return route.query.from === "screen" ? "map" : "library";
});
const backTarget = computed(() => ({ name: "screen", query: { ...(backView.value === "map" ? {} : { view: backView.value }), ...(backView.value !== "library" ? { video: videoId.value } : {}) } }));
const backLabel = computed(() => ({ map: "返回课程知识导航", library: "返回我的课程", analysis: "返回复习进度", weak: "返回待复习清单" })[backView.value]);

const processing = computed(() => Boolean(video.value && ["queued", "transcribing", "indexing"].includes(video.value.status)));
const canDelete = computed(() => Boolean(video.value && ["ready", "failed"].includes(video.value.status)));
const statusOptions: Array<{ label: string; value: VideoStatus }> = [
  { label: "等待处理", value: "queued" },
  { label: "正在转写", value: "transcribing" },
  { label: "正在整理", value: "indexing" },
  { label: "可以复习", value: "ready" },
  { label: "处理失败", value: "failed" },
];

function clearPoll() {
  if (pollTimer !== undefined) {
    window.clearTimeout(pollTimer);
    pollTimer = undefined;
  }
}

function schedulePoll() {
  clearPoll();
  if (disposed || !processing.value || document.hidden) return;
  pollTimer = window.setTimeout(async () => {
    pollTimer = undefined;
    if (!document.hidden) await refreshVideo();
  }, 2000);
}

async function loadContent() {
  if (contentLoading.value) return;
  contentLoading.value = true;
  contentError.value = "";
  const [transcriptResult, summaryResult] = await Promise.allSettled([
    api.getTranscript(videoId.value),
    api.getSummary(videoId.value),
  ]);
  if (transcriptResult.status === "fulfilled") {
    segments.value = transcriptResult.value.segments;
  } else {
    const error = toApiError(transcriptResult.reason);
    contentError.value = error.message;
  }
  if (summaryResult.status === "fulfilled") {
    chapters.value = summaryResult.value.chapters;
  } else {
    const error = toApiError(summaryResult.reason);
    if (!contentError.value) contentError.value = error.message;
  }
  contentLoaded.value = transcriptResult.status === "fulfilled" && summaryResult.status === "fulfilled";
  contentLoading.value = false;
}

async function refreshVideo(manual = false) {
  if (disposed || fetchInFlight) return;
  fetchInFlight = true;
  if (manual) refreshing.value = true;
  try {
    const nextVideo = await api.getVideo(videoId.value);
    if (disposed) return;
    const becameReady = nextVideo.status === "ready" && (!contentLoaded.value || video.value?.status !== "ready");
    video.value = nextVideo;
    initialError.value = "";
    initialLoading.value = false;
    connectionError.value = "";
    if (becameReady) await loadContent();
  } catch (error) {
    const apiError = toApiError(error);
    if (!video.value) {
      initialError.value = apiError.message;
    } else {
      connectionError.value = apiError.message;
    }
  } finally {
    fetchInFlight = false;
    initialLoading.value = false;
    refreshing.value = false;
    if (processing.value) schedulePoll();
    else clearPoll();
  }
}

function onVisibilityChange() {
  if (document.hidden) {
    clearPoll();
  } else if (processing.value) {
    void refreshVideo();
  }
}

function onNav(key: string) {
  router.push({ name: "screen", query: key === "map" ? {} : { view: key } });
}

function seekTo(seconds: number) {
  playerRef.value?.seekTo(seconds);
  const section = playerSection.value;
  const viewport = scrollArea.value?.getBoundingClientRect();
  if (!section || !viewport) return;
  const { top } = section.getBoundingClientRect();
  if (top < viewport.top || top >= viewport.bottom) {
    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    section.scrollIntoView({ behavior: reducedMotion ? "auto" : "smooth", block: "start" });
  }
}

async function retryVideo() {
  if (!video.value || retrying.value) return;
  try {
    await ElMessageBox.confirm(
      "重试会重新生成该视频的转写、章节提要和检索索引，并清空当前问答。是否继续？",
      "重新处理视频",
      { confirmButtonText: "开始重试", cancelButtonText: "取消", type: "warning" },
    );
  } catch {
    return;
  }
  retrying.value = true;
  try {
    const nextVideo = await api.retryVideo(video.value.id);
    video.value = nextVideo;
    segments.value = [];
    chapters.value = [];
    contentLoaded.value = false;
    contentError.value = "";
    ElMessage.success("已重新加入处理队列");
    await refreshVideo();
  } catch (error) {
    ElMessage.error(toApiError(error).message);
  } finally {
    retrying.value = false;
  }
}

async function deleteVideo() {
  if (!video.value || deleting.value) return;
  try {
    await ElMessageBox.confirm("删除该视频及其转写、提要和问答记录？", "确认删除", {
      confirmButtonText: "确认删除",
      cancelButtonText: "取消",
      type: "warning",
      confirmButtonClass: "el-button--danger",
    });
  } catch {
    return;
  }
  deleting.value = true;
  try {
    await api.deleteVideo(video.value.id);
    ElMessage.success("视频及相关记录已删除");
    await router.push(backTarget.value);
  } catch (error) {
    ElMessage.error(toApiError(error).message);
  } finally {
    deleting.value = false;
  }
}

async function changeMockStatus(value: VideoStatus) {
  if (!isMock || !video.value) return;
  try {
    const nextVideo = await mockApi.setVideoStatus(video.value.id, value);
    video.value = nextVideo;
    contentLoaded.value = false;
    contentError.value = "";
    segments.value = [];
    chapters.value = [];
    if (nextVideo.status === "ready") {
      await loadContent();
    }
    if (processing.value) schedulePoll();
    else clearPoll();
  } catch (error) {
    ElMessage.error(toApiError(error).message);
  }
}

watch(playerRef, (player) => {
  if (player && pendingStartAt !== null) {
    player.seekTo(pendingStartAt);
    pendingStartAt = null;
  }
}, { flush: "post" });

onMounted(() => {
  document.addEventListener("visibilitychange", onVisibilityChange);
  void refreshVideo();
});

onBeforeUnmount(() => {
  disposed = true;
  clearPoll();
  document.removeEventListener("visibilitychange", onVisibilityChange);
});
</script>

<template>
  <div class="scr-shell">
    <ScreenTopBar :active="backView" @nav="onNav" @exit="router.push('/')" />
    <main ref="scrollArea" class="scr-stage detail-page">
      <div class="container">
        <div class="detail-nav">
          <RouterLink :to="backTarget" class="back-link"><el-icon><ArrowLeft /></el-icon>{{ backLabel }}</RouterLink>
          <div v-if="isMock" class="demo-control">
            <span>演示状态</span>
            <el-select
              :model-value="video?.status"
              size="small"
              style="width: 116px"
              aria-label="切换演示处理状态"
              @change="changeMockStatus"
            >
              <el-option v-for="option in statusOptions" :key="option.value" :label="option.label" :value="option.value" />
            </el-select>
          </div>
        </div>

        <div v-if="initialLoading" class="panel detail-loading">
          <el-skeleton :rows="8" animated />
        </div>

        <section v-else-if="initialError || !video" class="panel initial-error">
          <span class="initial-error__icon"><WarningFilled /></span>
          <h1>无法打开这个视频</h1>
          <p>{{ initialError || "视频不存在或已删除" }}</p>
          <div class="initial-error__actions">
            <el-button :loading="refreshing" @click="refreshVideo(true)">重新加载</el-button>
            <el-button type="primary" @click="router.push(backTarget)">{{ backLabel }}</el-button>
          </div>
        </section>

        <template v-else>
          <header class="detail-head">
            <div class="detail-head__main">
              <div class="title-line">
                <h1>{{ video.title }}</h1>
                <StatusBadge :status="video.status" />
              </div>
              <div class="detail-meta">
                <span><el-icon><Clock /></el-icon>{{ formatDuration(video.duration_sec) }}</span>
                <span>{{ formatDate(video.created_at) }}</span>
                <span><el-icon><VideoCamera /></el-icon>仅音频转写模式</span>
                <span>第 {{ video.attempt }} 次处理</span>
                <span v-if="isMock">演示转写与问答</span>
              </div>
            </div>
            <el-button v-if="canDelete" class="detail-delete" :loading="deleting" @click="deleteVideo">
              <el-icon><Delete /></el-icon>删除视频
            </el-button>
          </header>

          <el-alert
            v-if="connectionError"
            class="connection-alert"
            :title="`连接中断：${connectionError}。页面保留最后一次成功获取的状态。`"
            type="warning"
            :closable="false"
            show-icon
          >
            <el-button size="small" @click="refreshVideo(true)">重新连接</el-button>
          </el-alert>

          <ProcessingPanel
            v-if="processing"
            :video="video"
            :refreshing="refreshing"
            @refresh="refreshVideo(true)"
          />

          <section v-else-if="video.status === 'failed'" class="panel failed-panel">
            <div class="failed-panel__main">
              <span class="failed-panel__icon"><WarningFilled /></span>
              <div>
                <span class="section-kicker">PROCESSING STOPPED</span>
                <h2>本次处理未完成</h2>
                <p>{{ video.error?.message || "视频处理失败，请稍后重新处理" }}</p>
                <span class="error-code">错误代码：{{ video.error?.code || "UNKNOWN_ERROR" }}</span>
              </div>
            </div>
            <div class="failed-panel__actions">
              <el-button v-if="video.error?.retryable" type="primary" :loading="retrying" @click="retryVideo">
                <el-icon><Refresh /></el-icon>重新处理
              </el-button>
              <el-button :loading="deleting" @click="deleteVideo"><el-icon><Delete /></el-icon>删除并更换文件</el-button>
            </div>
            <p class="failed-panel__note">
              {{ video.error?.retryable ? "旧转写、提要、索引和问答将在重试时重新生成。" : "此错误无法通过重试解决，请删除后更换视频文件。" }}
            </p>
          </section>

          <template v-else-if="video.status === 'ready'">
            <el-alert
              v-if="contentError"
              class="content-alert"
              :title="`部分复习内容加载失败：${contentError}`"
              type="warning"
              :closable="false"
              show-icon
            >
              <el-button size="small" @click="loadContent">重新加载内容</el-button>
            </el-alert>

            <div class="workspace">
              <div class="workspace__left">
                <section ref="playerSection" class="panel player-card">
                  <div class="card-title">
                    <div><span class="section-kicker">COURSE VIDEO</span><h2>课程播放</h2></div>
                    <span class="source-tag"><InfoFilled /> 点击时间点可定位</span>
                  </div>
                  <VideoPlayer ref="playerRef" :video="video" />
                  <TranscriptPanel
                    :segments="segments"
                    :loading="contentLoading"
                    :error="segments.length ? '' : contentError"
                    @seek="seekTo"
                  />
                </section>
              </div>

              <el-tabs v-model="activePanel" class="review-tabs" stretch aria-label="课程复习方式">
                <el-tab-pane label="章节提要" name="chapters">
                  <section class="panel chapter-card" aria-labelledby="chapter-title">
                    <div class="section-heading">
                      <div>
                        <span class="section-kicker">CHAPTERS</span>
                        <h3 id="chapter-title">章节提要</h3>
                        <p>每 60 秒选取课程原句，点击时间点回看</p>
                      </div>
                      <span class="extract-tag">提取式</span>
                    </div>
                    <ChapterList
                      :chapters="chapters"
                      :segments="segments"
                      :loading="contentLoading"
                      :error="chapters.length ? '' : contentError"
                      @seek="seekTo"
                    />
                  </section>
                </el-tab-pane>

                <el-tab-pane label="向课程提问" name="question">
                  <QuestionPanel
                    :key="`${video.id}-${video.attempt}`"
                    :video-id="video.id"
                    @seek="seekTo"
                  />
                </el-tab-pane>
              </el-tabs>
            </div>
          </template>
        </template>
      </div>
    </main>
  </div>
</template>

<style scoped>
.detail-page { overflow-y: auto; padding: 22px 0 26px; }
.detail-page > .container { width: 100%; max-width: 1480px; padding-inline: 26px; }
.detail-nav { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 8px; min-height: 32px; margin-bottom: 16px; }
.back-link { display: inline-flex; align-items: center; gap: 5px; color: #627a80; font-size: 12px; text-decoration: none; }
.back-link:hover { color: var(--teal); }
.demo-control { display: flex; align-items: center; gap: 7px; padding: 4px 5px 4px 10px; border: 1px solid #efe2c8; border-radius: 7px; background: #fffaf0; color: #8b713d; font-size: 10px; }
.detail-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 24px; margin: 0 2px 24px; }
.detail-head__main { min-width: 0; }
.title-line { display: flex; align-items: center; flex-wrap: wrap; gap: 13px; }
.title-line h1 { margin: 0; color: var(--ink); font-size: clamp(22px, 2.3vw, 28px); line-height: 1.4; font-weight: 720; overflow-wrap: anywhere; }
.detail-meta { display: flex; flex-wrap: wrap; align-items: center; gap: 6px 18px; margin-top: 11px; color: #74878e; font-size: 12px; }
.detail-meta span { display: inline-flex; align-items: center; gap: 4px; }
.detail-meta span + span::before { content: ""; width: 3px; height: 3px; border-radius: 50%; background: #b5c3c5; margin-right: 9px; }
.detail-meta svg { width: 13px; }
.detail-delete { color: #8e5c49; border-color: #e2d7d1; flex-shrink: 0; }
.connection-alert, .content-alert { margin-bottom: 16px; }
.workspace { display: grid; grid-template-columns: minmax(0, 1.08fr) minmax(0, 0.92fr); gap: 22px; align-items: start; }
.workspace__left, .review-tabs { min-width: 0; }
.player-card { padding: 22px; min-width: 0; scroll-margin-top: 15px; }
.review-tabs { --el-color-primary: var(--teal); }
.review-tabs :deep(.el-tabs__header) { margin: 0 0 12px; padding: 4px; border: 1px solid var(--line); border-radius: 10px; background: #fff; }
.review-tabs :deep(.el-tabs__nav-wrap::after), .review-tabs :deep(.el-tabs__active-bar) { display: none; }
.review-tabs :deep(.el-tabs__item) { height: 36px; padding: 0 8px; border-radius: 6px; color: var(--muted); }
.review-tabs :deep(.el-tabs__item.is-active) { background: var(--teal-soft); color: var(--teal-dark); font-weight: 700; }
.card-title { display: flex; align-items: flex-start; justify-content: space-between; gap: 14px; margin-bottom: 16px; }
.card-title h2 { margin: 0; color: var(--ink); font-size: 20px; }
.source-tag { display: inline-flex; align-items: center; gap: 4px; color: #819499; font-size: 11px; white-space: nowrap; }
.source-tag svg { width: 12px; }
.chapter-card { padding: 22px; min-width: 0; }
.chapter-card .section-heading { align-items: flex-start; margin-bottom: 8px; }
.extract-tag { flex-shrink: 0; padding: 3px 7px; border-radius: 4px; background: #f1f5f4; color: #799087; font-size: 9px; }
.processing-panel { margin-top: 0; }
.failed-panel { position: relative; padding: 26px; display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 20px; align-items: center; }
.failed-panel__main { display: flex; align-items: flex-start; gap: 14px; }
.failed-panel__icon, .initial-error__icon { width: 48px; height: 48px; display: grid; place-items: center; flex-shrink: 0; border-radius: 13px; background: #fff3ec; color: #ad5638; font-size: 22px; }
.failed-panel h2 { margin: 0; color: var(--ink); font-size: 20px; }
.failed-panel p { margin: 5px 0 6px; color: #865d4d; font-size: 13px; }
.error-code { color: #9b8e88; font-family: Consolas, monospace; font-size: 10px; }
.failed-panel__actions { display: flex; flex-direction: column; gap: 8px; }
.failed-panel__actions .el-button { margin-left: 0; }
.failed-panel__note { grid-column: 1 / -1; margin: 0; padding-top: 14px; border-top: 1px solid #f0e8e4; color: #8f817b; font-size: 11px; }
.detail-loading { padding: 28px; }
.initial-error { max-width: 520px; margin: 50px auto; padding: 38px; text-align: center; }
.initial-error__icon { margin: 0 auto 15px; }
.initial-error h1 { margin: 0; color: var(--ink); font-size: 23px; }
.initial-error p { margin: 7px 0 20px; color: var(--muted); font-size: 13px; overflow-wrap: anywhere; }
.initial-error__actions { display: flex; flex-wrap: wrap; justify-content: center; gap: 8px; }
.initial-error__actions .el-button { margin-left: 0; }
@media (max-width: 1080px) {
  .workspace { grid-template-columns: minmax(0, 1fr); }
  .review-tabs { grid-row: 1; }
}
@media (max-width: 900px) {
  .detail-page { padding-top: 16px; }
  .detail-page > .container { padding-inline: 14px; }
  .detail-head { margin-bottom: 18px; }
  .detail-meta span + span::before { display: none; }
  .detail-meta { gap: 5px 12px; }
}
@media (max-width: 700px) {
  .detail-head { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 8px; }
  .title-line { gap: 6px; }
  .title-line h1 { font-size: 20px; }
  .detail-meta { margin-top: 7px; }
  .detail-delete { padding-inline: 8px; }
  .failed-panel { grid-template-columns: 1fr; }
  .failed-panel__actions { flex-direction: row; flex-wrap: wrap; }
  .failed-panel__actions .el-button { flex: 1; }
  .player-card, .chapter-card { padding: 17px; }
  .source-tag { display: none; }
  .demo-control { padding-left: 7px; }
}
</style>

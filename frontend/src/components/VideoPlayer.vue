<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from "vue";
import { CircleCheck, VideoCamera } from "@element-plus/icons-vue";
import { api, isMock } from "@/api";
import { toApiError } from "@/api/http";
import type { Video } from "@/types";
import { formatDuration, formatTime } from "@/utils/format";

const props = defineProps<{ video: Video }>();
const videoElement = ref<HTMLVideoElement>();
const pendingSeekSec = ref<number | null>(null);
const notice = ref("");
const playerError = ref("");
const metadataReady = ref(false);
const saveState = ref<"idle" | "saving" | "saved" | "failed" | "expired">("idle");
const saveHint = ref("");
let progressVersion = 0;
let lastSavedSec = 0;
let lastSentAt = 0;
let saving = false;
let staleAttempt = false;
let explicitSeek = false;
let resumeApplied = false;
let disposed = false;

const SAVE_INTERVAL_MS = 15_000;
const MIN_SAVE_SECONDS = 1;

const contentUrl = computed(() => `/api/videos/${encodeURIComponent(props.video.id)}/content`);
const saveLabel = computed(() => {
  if (isMock) return "";
  return ({ idle: "", saving: "正在保存进度", saved: "进度已保存", failed: "进度保存失败", expired: "进度已在其他窗口更新" })[saveState.value];
});

function applyPendingSeek() {
  if (pendingSeekSec.value === null) return;
  const target = pendingSeekSec.value;
  pendingSeekSec.value = null;
  performSeek(target);
}

function performSeek(seconds: number) {
  const element = videoElement.value;
  if (!element) return;
  const maximum = Number.isFinite(element.duration) ? element.duration : props.video.duration_sec;
  const safeSeconds = Math.max(0, Math.min(seconds, maximum));
  element.currentTime = safeSeconds;
  element.pause();
  notice.value = `已定位至 ${formatTime(safeSeconds)}，点击播放继续`;
}

async function seekTo(seconds: number) {
  if (!Number.isFinite(seconds) || seconds < 0) return;
  if (isMock) {
    notice.value = `已定位至 ${formatTime(Math.min(seconds, props.video.duration_sec))}`;
    return;
  }
  explicitSeek = true;
  playerError.value = "";
  await nextTick();
  if (!videoElement.value || !metadataReady.value) {
    pendingSeekSec.value = seconds;
    notice.value = `视频就绪后将定位至 ${formatTime(seconds)}，点击播放继续`;
    return;
  }
  performSeek(seconds);
}

async function restoreProgress() {
  if (isMock || resumeApplied || explicitSeek || disposed) return;
  resumeApplied = true;
  try {
    const progress = await api.getProgress(props.video.id);
    progressVersion = progress.version;
    lastSavedSec = progress.position_sec;
    if (!progress.saved || progress.position_sec < MIN_SAVE_SECONDS) return;
    // 已接近结尾就不自动跳回，避免打开即“看完”。
    if (progress.position_sec >= props.video.duration_sec - 3) return;
    performSeek(progress.position_sec);
    notice.value = `已回到上次看到的位置 ${formatTime(progress.position_sec)}，点击播放继续`;
  } catch {
    // 读取失败不影响正常播放，下一次播放仍会尝试保存。
  }
}

async function persistProgress(force = false) {
  const element = videoElement.value;
  if (isMock || !element || saving || staleAttempt || props.video.status !== "ready") return;
  const position = element.currentTime;
  if (!Number.isFinite(position)) return;
  const now = Date.now();
  if (!force && now - lastSentAt < SAVE_INTERVAL_MS) return;
  if (!force && Math.abs(position - lastSavedSec) < 0.5) return;
  saving = true;
  lastSentAt = now;
  saveState.value = "saving";
  try {
    const saved = await api.saveProgress(props.video.id, {
      attempt: props.video.attempt,
      position_sec: position,
      expected_version: progressVersion,
    });
    progressVersion = saved.version;
    lastSavedSec = saved.position_sec;
    saveState.value = "saved";
    saveHint.value = "";
    return;
  } catch (error) {
    const apiError = toApiError(error);

    // 视频已重新处理：旧批次进度作废，重试没有意义，也不再反复提示。
    if (apiError.code === "STALE_ATTEMPT") {
      staleAttempt = true;
      saveState.value = "expired";
      saveHint.value = "这个视频已重新处理，旧进度已作废，本次未保存。刷新页面后可从头继续。";
      return;
    }

    // 版本冲突：多数是刷新瞬间新旧页面各存了一次，或是同一账号的另一个窗口。
    // 进度是"最后一次为准"的语义，重读版本后原样重试一次即可，正常情况用户无感。
    if (apiError.code === "VERSION_CONFLICT") {
      try {
        const latest = await api.getProgress(props.video.id);
        const retried = await api.saveProgress(props.video.id, {
          attempt: props.video.attempt,
          position_sec: position,
          expected_version: latest.version,
        });
        progressVersion = retried.version;
        lastSavedSec = retried.position_sec;
        saveState.value = "saved";
        saveHint.value = "";
        return;
      } catch (retryError) {
        const retryApiError = toApiError(retryError);
        if (retryApiError.code === "STALE_ATTEMPT") {
          staleAttempt = true;
          saveState.value = "expired";
          saveHint.value = "这个视频已重新处理，旧进度已作废，本次未保存。刷新页面后可从头继续。";
          return;
        }
        // 连续两次都被别人抢先，才提示；这种情况确实需要用户知道。
        saveState.value = "expired";
        saveHint.value = "进度正在另一个窗口被修改，本次未覆盖。刷新页面可取回最新位置。";
        try {
          progressVersion = (await api.getProgress(props.video.id)).version;
        } catch {
          progressVersion = 0;
        }
        return;
      }
    }

    saveState.value = "failed";
    saveHint.value = apiError.message;
  } finally {
    saving = false;
  }
}

function onMetadataLoaded() {
  metadataReady.value = true;
  applyPendingSeek();
  void restoreProgress();
}

function onVideoError() {
  metadataReady.value = false;
  playerError.value = "视频暂时无法加载，请确认文件仍在服务端并可访问";
}

function onPlay() {
  if (notice.value) notice.value = "";
}

function onTimeUpdate() {
  void persistProgress();
}

function onPause() {
  void persistProgress(true);
}

function onVisibilityChange() {
  if (document.hidden) void persistProgress(true);
}

watch(
  () => props.video.id,
  () => {
    pendingSeekSec.value = null;
    notice.value = "";
    playerError.value = "";
    metadataReady.value = false;
    progressVersion = 0;
    lastSavedSec = 0;
    lastSentAt = 0;
    explicitSeek = false;
    resumeApplied = false;
    staleAttempt = false;
    saveState.value = "idle";
    saveHint.value = "";
  },
);

document.addEventListener("visibilitychange", onVisibilityChange);
defineExpose({ seekTo });
onBeforeUnmount(() => {
  disposed = true;
  document.removeEventListener("visibilitychange", onVisibilityChange);
  void persistProgress(true);
  const element = videoElement.value;
  if (element) { element.pause(); element.removeAttribute("src"); element.load(); }
});
</script>

<template>
  <div class="player-wrap">
    <div class="player" :class="{ 'player--mock': isMock }">
      <video
        v-if="!isMock"
        ref="videoElement"
        :src="contentUrl"
        preload="metadata"
        controls
        playsinline
        @loadedmetadata="onMetadataLoaded"
        @error="onVideoError"
        @play="onPlay"
        @timeupdate="onTimeUpdate"
        @pause="onPause"
      >
        当前浏览器不支持 HTML5 视频播放。
      </video>
      <div v-else class="mock-player">
        <span class="mock-player__icon"><VideoCamera /></span>
        <strong>课程视频</strong>
        <p>演示模式不包含真实视频文件，播放器将在接入后端后启用。</p>
        <span class="mock-player__duration time-text">{{ formatDuration(video.duration_sec) }}</span>
      </div>
    </div>
    <div class="player-caption">
      <span class="player-caption__status">
        <el-icon><CircleCheck /></el-icon>
        仅使用音轨转写内容
      </span>
      <span class="player-caption__save" :class="`is-${saveState}`" aria-live="polite">
        <template v-if="saveLabel">{{ saveLabel }}</template>
        <template v-else>引用定位会暂停视频，由你决定何时继续</template>
      </span>
    </div>
    <el-alert v-if="saveHint" :title="saveHint" type="warning" :closable="false" show-icon />
    <el-alert v-if="playerError" :title="playerError" type="error" :closable="false" show-icon />
    <p v-if="notice" class="seek-notice" aria-live="polite">
      <span>{{ notice }}</span>
      <span v-if="isMock" class="seek-notice__mock">演示定位</span>
    </p>
  </div>
</template>

<style scoped>
.player-wrap { min-width: 0; }
.player { position: relative; overflow: hidden; aspect-ratio: 16 / 9; border-radius: 10px; background: #17353d; }
.player--mock { display: grid; min-height: 190px; }
.player video { display: block; width: 100%; height: 100%; object-fit: contain; background: #102b32; }
.mock-player { height: 100%; display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 20px; color: white; text-align: center; background: radial-gradient(circle at 50% 40%, #234952 0, #17353d 58%, #132f36 100%); }
.mock-player__icon { width: 56px; height: 56px; display: grid; place-items: center; border: 1px solid rgba(255,255,255,0.2); border-radius: 50%; background: rgba(255,255,255,0.08); color: #b9dfdc; font-size: 25px; }
.mock-player strong { margin-top: 12px; font-size: 15px; font-weight: 600; }
.mock-player p { max-width: 320px; margin: 5px 0 12px; color: #b7c8cb; font-size: 11px; line-height: 1.65; }
.mock-player__duration { padding: 3px 8px; border-radius: 5px; background: rgba(0,0,0,0.22); color: #e0eded; font-size: 11px; }
.player-caption { display: flex; justify-content: space-between; gap: 14px; padding: 11px 2px 0; color: #72868d; font-size: 11px; }
.player-caption__status { display: inline-flex; align-items: center; gap: 4px; color: #508071; }
.player-caption__status svg { width: 13px; }
.player-caption__save { color: #72868d; }
.player-caption__save.is-saving { color: #8d774a; }
.player-caption__save.is-saved { color: #508071; }
.player-caption__save.is-failed, .player-caption__save.is-expired { color: #ad5638; }
.seek-notice { display: flex; align-items: center; justify-content: space-between; gap: 10px; margin: 12px 0 0; padding: 8px 11px; border: 1px solid #d3e5df; border-radius: 7px; background: #f1f9f5; color: #326c5d; font-size: 12px; }
.seek-notice__mock { color: #8d774a; font-size: 10px; white-space: nowrap; }
.el-alert { margin-top: 10px; }
@media (max-width: 850px) { .player-caption { flex-direction: column; gap: 2px; } }
@media (max-width: 520px) {
  .mock-player { padding: 12px; }
  .mock-player__icon { width: 40px; height: 40px; flex-shrink: 0; font-size: 20px; }
}
</style>

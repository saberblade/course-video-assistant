<script setup lang="ts">
import { computed, nextTick, ref, watch } from "vue";
import { CircleCheck, VideoCamera } from "@element-plus/icons-vue";
import { isMock } from "@/api";
import type { Video } from "@/types";
import { formatDuration, formatTime } from "@/utils/format";

const props = defineProps<{ video: Video }>();
const videoElement = ref<HTMLVideoElement>();
const pendingSeekSec = ref<number | null>(null);
const notice = ref("");
const playerError = ref("");
const metadataReady = ref(false);

const contentUrl = computed(() => `/api/videos/${encodeURIComponent(props.video.id)}/content`);

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
  playerError.value = "";
  await nextTick();
  if (!videoElement.value || !metadataReady.value) {
    pendingSeekSec.value = seconds;
    notice.value = `视频就绪后将定位至 ${formatTime(seconds)}，点击播放继续`;
    return;
  }
  performSeek(seconds);
}

function onMetadataLoaded() {
  metadataReady.value = true;
  applyPendingSeek();
}

function onVideoError() {
  metadataReady.value = false;
  playerError.value = "视频暂时无法加载，请确认文件仍在服务端并可访问";
}

function onPlay() {
  if (notice.value) notice.value = "";
}

watch(
  () => props.video.id,
  () => {
    pendingSeekSec.value = null;
    notice.value = "";
    playerError.value = "";
    metadataReady.value = false;
  },
);

defineExpose({ seekTo });
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
      <span>引用定位会暂停视频，由你决定何时继续</span>
    </div>
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
.seek-notice { display: flex; align-items: center; justify-content: space-between; gap: 10px; margin: 12px 0 0; padding: 8px 11px; border: 1px solid #d3e5df; border-radius: 7px; background: #f1f9f5; color: #326c5d; font-size: 12px; }
.seek-notice__mock { color: #8d774a; font-size: 10px; white-space: nowrap; }
.el-alert { margin-top: 10px; }
@media (max-width: 850px) { .player-caption { flex-direction: column; gap: 2px; } }
@media (max-width: 520px) {
  .mock-player { padding: 12px; }
  .mock-player__icon { width: 40px; height: 40px; flex-shrink: 0; font-size: 20px; }
}
</style>

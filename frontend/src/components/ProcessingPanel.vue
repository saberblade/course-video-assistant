<script setup lang="ts">
import { computed } from "vue";
import { Clock, Refresh, VideoCamera } from "@element-plus/icons-vue";
import type { Video, VideoStatus } from "@/types";
import { elapsedText, statusMeta } from "@/utils/format";

const props = defineProps<{ video: Video; refreshing: boolean }>();
const emit = defineEmits<{ refresh: [] }>();

const steps: Array<{ key: VideoStatus; label: string }> = [
  { key: "queued", label: "排队等待" },
  { key: "transcribing", label: "音轨转写" },
  { key: "indexing", label: "整理索引" },
  { key: "ready", label: "准备完成" },
];
const activeIndex = computed(() => steps.findIndex((step) => step.key === props.video.status));
</script>

<template>
  <section class="panel processing-panel" aria-live="polite">
    <div class="processing-panel__top">
      <div class="processing-panel__identity">
        <span class="processing-panel__icon"><VideoCamera /></span>
        <div>
          <span class="section-kicker">PROCESSING</span>
          <h2>{{ statusMeta[video.status].label }}</h2>
          <p>{{ statusMeta[video.status].description }}</p>
        </div>
      </div>
      <div class="processing-panel__actions">
        <span class="elapsed"><el-icon><Clock /></el-icon>{{ elapsedText(video) }}</span>
        <el-button :loading="refreshing" @click="emit('refresh')"><el-icon><Refresh /></el-icon>刷新状态</el-button>
      </div>
    </div>

    <div class="steps">
      <div
        v-for="(step, index) in steps"
        :key="step.key"
        class="step"
        :class="{ 'step--done': index < activeIndex, 'step--active': index === activeIndex }"
      >
        <span class="step__dot">{{ index < activeIndex ? "✓" : index + 1 }}</span>
        <span>{{ step.label }}</span>
        <i v-if="index < steps.length - 1" />
      </div>
    </div>

    <div class="processing-note">
      <span class="pulse-dot" />
      <span>视频播放器、原文转写与章节提要将在此页面自动加载，无需手动刷新。</span>
      <span class="processing-note__mock">状态每 2 秒更新</span>
    </div>
  </section>
</template>

<style scoped>
.processing-panel { padding: 26px; }
.processing-panel__top { display: flex; align-items: flex-start; justify-content: space-between; gap: 20px; }
.processing-panel__identity { display: flex; gap: 15px; }
.processing-panel__icon { width: 48px; height: 48px; display: grid; place-items: center; flex-shrink: 0; border-radius: 13px; background: #eaf6f4; color: var(--teal); font-size: 23px; }
.processing-panel h2 { margin: 0; color: var(--ink); font-size: 21px; }
.processing-panel h2 + p { margin: 4px 0 0; color: var(--muted); font-size: 13px; }
.processing-panel__actions { display: flex; align-items: center; gap: 14px; flex-shrink: 0; }
.elapsed { display: inline-flex; align-items: center; gap: 5px; color: #71868d; font-size: 12px; }
.elapsed svg { width: 13px; }
.steps { display: flex; align-items: center; max-width: 740px; margin: 34px 0 28px; padding-left: 3px; }
.step { display: flex; align-items: center; gap: 7px; color: #98a8ac; font-size: 12px; white-space: nowrap; }
.step__dot { width: 23px; height: 23px; display: grid; place-items: center; border: 1px solid #d8e2e3; border-radius: 50%; font-family: Consolas, monospace; font-size: 10px; }
.step i { width: clamp(24px, 5vw, 64px); height: 1px; margin: 0 10px; background: #e0e8e9; }
.step--done { color: #5e8f87; }
.step--done .step__dot { border-color: #9dcac2; background: #edf8f4; color: #187761; }
.step--active { color: var(--teal); font-weight: 600; }
.step--active .step__dot { border-color: var(--teal); background: var(--teal); color: white; box-shadow: 0 0 0 4px #e6f4f2; }
.processing-note { display: flex; align-items: center; gap: 9px; padding: 14px 16px; border-radius: 9px; background: #f6faf9; color: #557078; font-size: 12px; }
.pulse-dot { width: 7px; height: 7px; border-radius: 50%; background: #37a189; box-shadow: 0 0 0 4px rgba(55,161,137,0.1); }
.processing-note__mock { margin-left: auto; color: #96a5a8; font-size: 11px; white-space: nowrap; }
@media (max-width: 700px) {
  .processing-panel { padding: 19px; }
  .processing-panel__top { flex-direction: column; }
  .processing-panel__actions { width: 100%; justify-content: space-between; }
  .steps { overflow-x: auto; padding-bottom: 5px; }
  .step i { min-width: 15px; }
  .processing-note { align-items: flex-start; line-height: 1.6; }
  .processing-note__mock { display: none; }
}
</style>

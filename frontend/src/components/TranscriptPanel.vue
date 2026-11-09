<script setup lang="ts">
import { Document, Position } from "@element-plus/icons-vue";
import type { TranscriptSegment } from "@/types";
import { formatTime } from "@/utils/format";

defineProps<{
  segments: TranscriptSegment[];
  loading: boolean;
  error: string;
}>();

const emit = defineEmits<{ seek: [seconds: number] }>();
</script>

<template>
  <div class="transcript-panel">
    <el-skeleton v-if="loading" :rows="5" animated />
    <el-alert v-else-if="error" :title="error" type="warning" :closable="false" show-icon />
    <details v-else class="transcript" :open="false">
      <summary>
        <span class="transcript__heading"><el-icon><Document /></el-icon>完整原文转写</span>
        <span class="transcript__count">{{ segments.length }} 个片段</span>
        <span class="transcript__arrow">展开</span>
      </summary>
      <div class="transcript__body">
        <p class="transcript__hint">点击任意时间点，回到老师讲到这句话的位置</p>
        <button
          v-for="segment in segments"
          :key="segment.id"
          type="button"
          class="segment"
          @click="emit('seek', segment.start_sec)"
        >
          <span class="segment__time time-text"><el-icon><Position /></el-icon>{{ formatTime(segment.start_sec) }}</span>
          <span class="segment__text">{{ segment.text }}</span>
        </button>
      </div>
    </details>
  </div>
</template>

<style scoped>
.transcript { border-top: 1px solid #edf1f1; }
.transcript summary { display: flex; align-items: center; gap: 10px; padding: 15px 0 3px; cursor: pointer; list-style: none; color: #526b73; font-size: 12px; }
.transcript summary::-webkit-details-marker { display: none; }
.transcript summary:hover { color: var(--teal); }
.transcript__heading { display: inline-flex; align-items: center; gap: 6px; color: var(--ink); font-size: 13px; font-weight: 650; }
.transcript__count { color: #8b9ba0; font-size: 11px; }
.transcript__arrow { margin-left: auto; color: var(--teal); font-size: 11px; }
.transcript[open] .transcript__arrow { font-size: 0; }
.transcript[open] .transcript__arrow::after { content: "收起"; font-size: 11px; }
.transcript__body { max-height: 370px; overflow-y: auto; padding: 8px 4px 4px 0; }
.transcript__hint { margin: 3px 0 12px; color: #8a9ba0; font-size: 11px; }
.segment { width: 100%; display: grid; grid-template-columns: 63px minmax(0, 1fr); align-items: flex-start; gap: 7px; padding: 9px 7px; border: 0; border-radius: 7px; background: transparent; color: #2e4851; text-align: left; cursor: pointer; transition: background 0.16s ease; }
.segment:hover { background: #f0f7f6; }
.segment__time { display: inline-flex; align-items: center; gap: 3px; padding-top: 2px; color: var(--teal); font-size: 11px; }
.segment__time svg { width: 12px; }
.segment__text { font-size: 13px; line-height: 1.75; overflow-wrap: anywhere; }
</style>

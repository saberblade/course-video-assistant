<script setup lang="ts">
import { computed } from "vue";
import { CircleCheck, Clock, Loading, Warning } from "@element-plus/icons-vue";
import type { VideoStatus } from "@/types";
import { statusMeta } from "@/utils/format";

const props = defineProps<{ status: VideoStatus }>();
const meta = computed(() => statusMeta[props.status]);
const icon = computed(() => {
  if (props.status === "ready") return CircleCheck;
  if (props.status === "failed") return Warning;
  if (props.status === "queued") return Clock;
  return Loading;
});
</script>

<template>
  <span class="status-badge" :class="`status-badge--${status}`">
    <el-icon :class="{ 'is-loading': status === 'transcribing' || status === 'indexing' }"><component :is="icon" /></el-icon>
    {{ meta.label }}
  </span>
</template>

<style scoped>
.status-badge { display: inline-flex; align-items: center; gap: 6px; width: fit-content; border-radius: 99px; padding: 4px 10px; font-size: 12px; font-weight: 600; white-space: nowrap; background: #f1f5f6; color: #496872; }
.status-badge--ready { background: #edf8f3; color: #14735c; }
.status-badge--failed { background: #fff2ed; color: #a64c2e; }
.status-badge--transcribing, .status-badge--indexing { background: #edf6f8; color: #247083; }
</style>

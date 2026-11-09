<script setup lang="ts">
import { ArrowRight, Clock, Delete, Film, VideoCamera } from "@element-plus/icons-vue";
import StatusBadge from "./StatusBadge.vue";
import type { Video } from "@/types";
import { formatBytes, formatDate, formatDuration } from "@/utils/format";

defineProps<{
  items: Video[];
  deletingId: string;
}>();

const emit = defineEmits<{
  open: [video: Video];
  delete: [video: Video];
}>();
</script>

<template>
  <div class="video-list">
    <div v-if="items.length" class="video-list__head" aria-hidden="true">
      <span>课程</span><span>时长</span><span>创建时间</span><span>当前阶段</span><span>操作</span>
    </div>
    <div v-for="video in items" :key="video.id" class="video-row" @click="emit('open', video)">
      <div class="video-row__title">
        <span class="video-row__icon"><VideoCamera /></span>
        <div>
          <strong :title="video.title">{{ video.title }}</strong>
          <span>第 {{ video.attempt }} 次处理 · {{ formatBytes(video.size_bytes) }}</span>
        </div>
      </div>
      <span class="video-row__duration time-text" data-label="时长"><Clock />{{ formatDuration(video.duration_sec) }}</span>
      <span class="video-row__date" data-label="创建时间">{{ formatDate(video.created_at) }}</span>
      <span data-label="当前阶段"><StatusBadge :status="video.status" /></span>
      <div class="video-row__actions">
        <el-button type="primary" text @click.stop="emit('open', video)">
          打开<el-icon class="el-icon--right"><ArrowRight /></el-icon>
        </el-button>
        <el-button
          v-if="video.status === 'ready' || video.status === 'failed'"
          class="delete-button"
          text
          :loading="deletingId === video.id"
          @click.stop="emit('delete', video)"
        >
          <el-icon><Delete /></el-icon>删除
        </el-button>
      </div>
    </div>
    <div v-if="!items.length" class="empty-state">
      <span class="empty-state__art"><Film /></span>
      <h3>还没有课程视频</h3>
      <p>上传第一段中文课程视频，开始建立你的复习线索。</p>
    </div>
  </div>
</template>

<style scoped>
.video-list { container-type: inline-size; }
.video-list__head, .video-row { display: grid; grid-template-columns: minmax(0, 1fr) 90px 130px 110px 150px; align-items: center; gap: 12px; }
.video-list__head { padding: 0 20px 12px; color: #7a8e95; font-size: 11px; }
.video-list__head span:last-child { text-align: right; }
.video-row { min-height: 88px; padding: 15px 20px; border-top: 1px solid #edf1f1; cursor: pointer; transition: background 0.18s ease; }
.video-row:hover { background: #fafcfc; }
.video-row__title { min-width: 0; display: flex; align-items: center; gap: 12px; }
.video-row__icon { width: 42px; height: 42px; flex-shrink: 0; display: grid; place-items: center; border-radius: 11px; background: #eef6f5; color: var(--teal); font-size: 20px; }
.video-row__title > div { min-width: 0; }
.video-row__title strong { display: block; overflow: hidden; color: var(--ink); font-size: 14px; font-weight: 650; text-overflow: ellipsis; white-space: nowrap; }
.video-row__title > div span { color: var(--muted); font-size: 12px; }
.video-row__duration { display: inline-flex; align-items: center; gap: 5px; color: #4e6972; font-size: 13px; }
.video-row__duration svg { width: 13px; }
.video-row__date { color: var(--muted); font-size: 12px; }
.video-row__actions { display: flex; justify-content: flex-end; align-items: center; gap: 1px; }
.delete-button { color: #9a654f; }
.empty-state { padding: 48px 20px 52px; border-top: 1px solid #edf1f1; text-align: center; }
.empty-state__art { width: 66px; height: 66px; display: grid; place-items: center; margin: 0 auto 16px; border-radius: 20px; background: #f0f6f5; color: #6a9896; font-size: 30px; transform: rotate(-3deg); }
.empty-state h3 { margin: 0; color: var(--ink); font-size: 17px; }
.empty-state p { margin: 7px 0 0; color: var(--muted); font-size: 13px; }
@container (max-width: 860px) {
  .video-list__head, .video-row { grid-template-columns: minmax(0, 1fr) 74px 110px 104px 132px; gap: 9px; }
}
@container (max-width: 640px) {
  .video-list__head { display: none; }
  .video-row {
    grid-template-columns: minmax(0, 1fr) auto;
    grid-template-areas:
      "title title"
      "duration status"
      "date actions";
    align-items: center;
    gap: 6px 10px;
    padding: 17px 14px;
  }
  .video-row__title { grid-area: title; }
  .video-row__title strong { overflow-wrap: anywhere; white-space: normal; }
  .video-row__duration { grid-area: duration; display: inline-flex; color: #637b82; font-size: 12px; }
  .video-row__date { grid-area: date; display: block; color: #87999e; font-size: 11px; }
  .video-row > [data-label="当前阶段"] { grid-area: status; justify-self: end; }
  .video-row__actions { grid-area: actions; gap: 0; }
  .video-row__actions .el-button { padding: 5px 7px; }
}
</style>

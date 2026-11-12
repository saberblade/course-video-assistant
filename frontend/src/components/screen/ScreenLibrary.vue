<script setup lang="ts">
import { computed, ref } from "vue";
import { Refresh } from "@element-plus/icons-vue";
import { ElMessage, ElMessageBox } from "element-plus";
import UploadPanel from "@/components/UploadPanel.vue";
import VideoList from "@/components/VideoList.vue";
import { api } from "@/api";
import { toApiError } from "@/api/http";
import type { Video } from "@/types";
import { formatDuration } from "@/utils/format";

const props = defineProps<{
  videos: Video[];
  loading: boolean;
  loadError: string;
  total: number;
  page: number;
  pageSize: number;
  readyVideo: Video | null;
}>();
const emit = defineEmits<{ refresh: []; page: [value: number]; open: [video: Video] }>();

const deletingId = ref("");
const readyCount = computed(() => props.videos.filter((video) => video.status === "ready").length);
const runningCount = computed(() =>
  props.videos.filter((video) => ["queued", "transcribing", "indexing"].includes(video.status)).length,
);
const totalDuration = computed(() => props.videos.reduce((sum, video) => sum + video.duration_sec, 0));
const pageLabel = computed(() => (props.total > props.pageSize ? "本页" : ""));

async function removeVideo(video: Video) {
  if (deletingId.value) return;
  deletingId.value = video.id;
  const fullscreen = document.fullscreenElement;
  try {
    const confirmed = await ElMessageBox.confirm("删除该视频及其转写、提要和问答记录？", "确认删除", {
      confirmButtonText: "确认删除",
      cancelButtonText: "取消",
      type: "warning",
      confirmButtonClass: "el-button--danger",
      appendTo: fullscreen instanceof HTMLElement ? fullscreen : undefined,
    }).catch(() => false);
    if (!confirmed) return;
    await api.deleteVideo(video.id);
    ElMessage.success("视频及相关记录已删除");
    emit("refresh");
  } catch (error) {
    ElMessage.error(toApiError(error).message);
  } finally {
    deletingId.value = "";
  }
}
</script>

<template>
  <section class="lib" aria-labelledby="library-title">
    <header class="lib-head">
      <div>
        <span class="section-kicker">MY COURSES</span>
        <h1 id="library-title">我的课程</h1>
        <p>上传课程视频并查看处理进度。处理完成后，可以查看提要、提问并按引用回看。</p>
      </div>
    </header>

    <dl class="lib-kpis" aria-label="课程概览">
      <div><dt>课程总数</dt><dd>{{ total }}</dd></div>
      <div><dt>{{ pageLabel }}可复习</dt><dd class="lib-kpis__ready">{{ readyCount }}</dd></div>
      <div><dt>{{ pageLabel }}处理中</dt><dd class="lib-kpis__running">{{ runningCount }}</dd></div>
      <div><dt>{{ pageLabel || "累计" }}时长</dt><dd>{{ totalDuration ? formatDuration(totalDuration) : "--:--" }}</dd></div>
    </dl>

    <section v-if="readyVideo" class="panel lib-resume" aria-label="最近可复习的课程">
      <div class="lib-resume__course">
        <strong :title="readyVideo.title">{{ readyVideo.title }}</strong>
        <span>最近上传的可复习课程 · {{ formatDuration(readyVideo.duration_sec) }}</span>
      </div>
      <el-button type="primary" @click="emit('open', readyVideo)">开始复习</el-button>
    </section>

    <div class="lib-body">
      <UploadPanel @uploaded="emit('open', $event)" />

      <section class="panel lib-list" aria-labelledby="video-list-title" :aria-busy="loading">
        <div class="section-heading lib-list__head">
          <div>
            <h2 id="video-list-title">课程列表</h2>
            <p>打开课程可查看视频和处理状态</p>
          </div>
          <el-button :loading="loading" @click="emit('refresh')">
            <el-icon><Refresh /></el-icon>刷新列表
          </el-button>
        </div>

        <el-alert
          v-if="loadError"
          class="lib-list__error"
          :title="'课程列表加载失败。' + loadError"
          type="error"
          show-icon
          :closable="false"
        />

        <div v-if="loading" class="lib-list__loading" aria-label="正在加载课程列表">
          <el-skeleton :rows="3" animated />
        </div>
        <VideoList
          v-else-if="!loadError || videos.length"
          :items="videos"
          :deleting-id="deletingId"
          @open="emit('open', $event)"
          @delete="removeVideo"
        />

        <div v-if="total > pageSize" class="lib-list__pagination">
          <el-pagination
            background
            size="small"
            layout="prev, pager, next"
            :pager-count="5"
            :total="total"
            :page-size="pageSize"
            :current-page="page"
            :disabled="loading"
            @current-change="emit('page', $event)"
          />
        </div>
      </section>
    </div>
  </section>
</template>

<style scoped>
.lib {
  display: grid;
  gap: 22px;
  max-width: 1440px;
  margin: 0 auto;
  padding: 30px 36px 32px;
}
/* 与 .rw（知识导航/复习进度/待复习清单）保持同一套标题尺度与节奏 */
.lib-head { display: flex; align-items: center; justify-content: space-between; gap: 20px; }
.lib-head h1 {
  margin: 5px 0 6px;
  color: var(--scr-text);
  font-size: clamp(24px, 2.4vw, 32px);
  letter-spacing: -0.7px;
  line-height: 1.4;
}
.lib-head p { margin: 0; color: #71858c; font-size: 13px; }

/* KPI 与复习进度的统计卡同一套观感：白卡 + 大号等宽数字 */
.lib-kpis {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 14px;
  margin: 0;
}
.lib-kpis div {
  padding: 18px 22px;
  border: 1px solid #e0e9e6;
  border-radius: 13px;
  background: #fff;
}
.lib-kpis dt { color: #738c8a; font-size: 12px; }
.lib-kpis dd {
  margin: 6px 0 0;
  color: #1b5556;
  font-family: "Bahnschrift", Consolas, monospace;
  font-size: 30px;
  font-weight: 600;
  line-height: 1.15;
}
.lib-kpis .lib-kpis__ready { color: var(--scr-green); }
.lib-kpis .lib-kpis__running { color: var(--scr-amber); }

.lib-resume {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 16px;
  border-left: 3px solid var(--scr-accent);
}
.lib-resume__course { display: grid; gap: 3px; min-width: 0; }
.lib-resume__course strong { overflow: hidden; color: var(--ink); text-overflow: ellipsis; white-space: nowrap; }
.lib-resume__course span { color: var(--muted); font-size: 12px; }
.lib-resume .el-button { flex-shrink: 0; }

.lib-body {
  display: grid;
  grid-template-columns: 320px minmax(0, 1fr);
  align-items: start;
  gap: 18px;
}
.lib-list { min-width: 0; }
.lib-list__head { align-items: center; padding: 18px 20px; }
.lib-list__head .el-button { flex-shrink: 0; }
.lib-list__loading { padding: 12px 20px 20px; border-top: 1px solid var(--line); }
.lib-list__error { width: auto; margin: 0 16px 16px; }
.lib-list__pagination { display: flex; justify-content: flex-end; padding: 14px; border-top: 1px solid var(--line); }

@media (max-width: 1180px) {
  .lib-body { grid-template-columns: 280px minmax(0, 1fr); }
}
@media (max-width: 1050px) {
  .lib { padding: 25px 24px; }
  .lib-kpis { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@media (max-width: 900px) {
  .lib-head { display: block; }
  .lib-body { grid-template-columns: minmax(0, 1fr); }
}
@media (max-width: 700px) {
  .lib { gap: 16px; padding: 22px 16px 30px; }
  .lib-head h1 { font-size: 26px; }
  .lib-kpis { gap: 10px; }
  .lib-kpis div { padding: 16px 18px; }
  .lib-kpis dd { font-size: 26px; }
}
@media (max-width: 440px) {
  .lib-kpis div { padding: 14px 12px; }
  .lib-list__head { padding: 16px 14px; }
  .lib-list__head h2 { font-size: 19px; }
  .lib-list__head p { font-size: 12px; }
  .lib-list__head .el-button { padding-inline: 8px; }
}
</style>

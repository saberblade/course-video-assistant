<script setup lang="ts">
import { computed, ref } from "vue";
import { Refresh } from "@element-plus/icons-vue";
import { ElMessage, ElMessageBox } from "element-plus";
import UploadPanel from "@/components/UploadPanel.vue";
import VideoList from "@/components/VideoList.vue";
import { api, isMock } from "@/api";
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
        <span class="section-kicker">MY COURSES · {{ isMock ? "演示数据" : "真实接口" }}</span>
        <h1 id="library-title">我的课程</h1>
        <p>上传课程视频并查看处理进度。处理完成后，可以查看提要、提问并按引用回看。</p>
      </div>
      <dl class="lib-kpis">
        <div><dt>课程总数</dt><dd>{{ total }}</dd></div>
        <div><dt>{{ pageLabel }}可复习</dt><dd class="lib-kpis__ready">{{ readyCount }}</dd></div>
        <div><dt>{{ pageLabel }}处理中</dt><dd class="lib-kpis__running">{{ runningCount }}</dd></div>
        <div><dt>{{ pageLabel || "累计" }}时长</dt><dd>{{ totalDuration ? formatDuration(totalDuration) : "--:--" }}</dd></div>
      </dl>
    </header>

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
  gap: 18px;
  max-width: 1480px;
  margin: 0 auto;
  padding: 22px 26px 26px;
}
.lib-head {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 18px;
  padding-bottom: 16px;
  border-bottom: 1px solid var(--scr-line);
}
.lib-head h1 { margin: 0 0 3px; color: var(--scr-text); font-size: 26px; line-height: 1.4; }
.lib-head p { margin: 0; color: var(--scr-text-dim); font-size: 13px; }
.lib-kpis {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 1px;
  flex-shrink: 0;
  margin: 0;
  overflow: hidden;
  border: 1px solid var(--scr-line);
  border-radius: 9px;
  background: var(--scr-line);
}
.lib-kpis div { padding: 8px 14px; background: #fff; }
.lib-kpis dt { color: var(--scr-text-dim); font-size: 11px; }
.lib-kpis dd {
  margin: 2px 0 0;
  color: var(--scr-text);
  font-family: "Bahnschrift", Consolas, monospace;
  font-size: 18px;
  line-height: 1.2;
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
@media (max-width: 900px) {
  .lib { padding: 16px 14px 22px; }
  .lib-head { flex-direction: column; align-items: stretch; }
  .lib-body { grid-template-columns: minmax(0, 1fr); }
}
@media (max-width: 440px) {
  .lib-kpis div { padding: 8px; }
  .lib-list__head { padding: 16px 14px; }
  .lib-list__head h2 { font-size: 19px; }
  .lib-list__head p { font-size: 12px; }
  .lib-list__head .el-button { padding-inline: 8px; }
}
</style>

<script setup lang="ts">
import { computed, ref } from "vue";
import { Check, Document, FolderOpened, UploadFilled } from "@element-plus/icons-vue";
import { ElMessage } from "element-plus";
import { api, isMock } from "@/api";
import { toApiError } from "@/api/http";
import type { Video } from "@/types";
import { formatBytes, validateFile } from "@/utils/format";

const emit = defineEmits<{ uploaded: [video: Video] }>();
const fileInput = ref<HTMLInputElement>();
const selectedFile = ref<File | null>(null);
const validationError = ref("");
const uploadError = ref("");
const uploading = ref(false);
const progress = ref(0);
const dragging = ref(false);
const fileError = computed(() => validationError.value || uploadError.value);

function chooseFile(file?: File) {
  if (!file || uploading.value) return;
  selectedFile.value = file;
  validationError.value = validateFile(file);
  uploadError.value = "";
  progress.value = 0;
}

function onInputChange(event: Event) {
  const input = event.target as HTMLInputElement;
  chooseFile(input.files?.[0]);
  input.value = "";
}

function onDrop(event: DragEvent) {
  dragging.value = false;
  chooseFile(event.dataTransfer?.files?.[0]);
}

async function submit() {
  if (!selectedFile.value || uploading.value) return;
  validationError.value = validateFile(selectedFile.value);
  if (validationError.value) return;
  uploading.value = true;
  uploadError.value = "";
  progress.value = 0;
  try {
    const video = await api.uploadVideo(selectedFile.value, (event) => {
      progress.value = Math.min(100, Math.round((event.loaded / event.total) * 100));
    });
    ElMessage.success("视频已加入处理队列");
    emit("uploaded", video);
  } catch (error) {
    const apiError = toApiError(error);
    uploadError.value = apiError.requestId
      ? `${apiError.message}（问题编号：${apiError.requestId}）`
      : apiError.message;
  } finally {
    uploading.value = false;
  }
}
</script>

<template>
  <section class="panel upload-panel" aria-labelledby="upload-title">
    <div class="section-heading">
      <div>
        <span class="section-kicker">NEW COURSE</span>
        <h2 id="upload-title">上传课程视频</h2>
        <p>从讲课音轨提取原文，建立可定位的复习线索</p>
      </div>
    </div>

    <div
      class="dropzone"
      :class="{ 'dropzone--active': dragging, 'dropzone--disabled': uploading }"
      @dragover.prevent="dragging = true"
      @dragleave.prevent="dragging = false"
      @drop.prevent="onDrop"
    >
      <input ref="fileInput" type="file" accept=".mp4,video/mp4" hidden @change="onInputChange" />
      <span class="dropzone__icon"><UploadFilled /></span>
      <template v-if="!selectedFile">
        <strong>拖拽视频到这里</strong>
        <span>或从电脑中选择文件</span>
        <el-button :disabled="uploading" @click="fileInput?.click()">
          <el-icon><FolderOpened /></el-icon>选择 MP4 视频
        </el-button>
      </template>
      <template v-else>
        <div class="selected-file">
          <span class="selected-file__icon"><Document /></span>
          <div>
            <strong :title="selectedFile.name">{{ selectedFile.name }}</strong>
            <span>{{ formatBytes(selectedFile.size) }}<template v-if="!validationError"> · 已通过基础检查</template></span>
          </div>
          <el-icon v-if="!validationError" class="selected-file__check"><Check /></el-icon>
        </div>
        <el-button text :disabled="uploading" @click="fileInput?.click()">重新选择</el-button>
      </template>
    </div>

    <p v-if="fileError" class="upload-error" role="alert">{{ fileError }}</p>

    <div v-if="uploading && !isMock" class="upload-progress" aria-live="polite">
      <div><span>正在上传视频</span><strong>{{ progress }}%</strong></div>
      <el-progress :percentage="progress" :show-text="false" :stroke-width="7" />
      <small>仅为上传字节进度，不代表视频处理进度</small>
    </div>
    <p v-else-if="uploading && isMock" class="mock-uploading">正在创建演示任务，不会实际上传文件…</p>

    <el-button
      class="submit-button"
      type="primary"
      size="large"
      :loading="uploading"
      :disabled="!selectedFile || Boolean(validationError)"
      @click="submit"
    >
      {{ uploading ? "正在提交" : "开始处理" }}
      <el-icon v-if="!uploading" class="el-icon--right"><UploadFilled /></el-icon>
    </el-button>

    <ul class="upload-rules" aria-label="上传要求">
      <li>MP4 · H.264 · AAC</li>
      <li>不超过 200 MiB / 20 分钟</li>
      <li>清晰中文讲课音轨</li>
    </ul>
  </section>
</template>

<style scoped>
.upload-panel { padding: 22px; }
.dropzone { margin-top: 16px; min-height: 174px; padding: 14px; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 8px; border: 1.5px dashed #a8c1c5; border-radius: 12px; background: #f7faf9; text-align: center; transition: 0.2s ease; }
.dropzone--active { border-color: var(--teal); background: #eef8f6; transform: translateY(-1px); }
.dropzone--disabled { opacity: 0.72; }
.dropzone__icon { width: 44px; height: 44px; display: grid; place-items: center; margin-bottom: 4px; border-radius: 13px; background: #e5f2f0; color: var(--teal); font-size: 23px; }
.dropzone > strong { color: var(--ink); font-size: 15px; }
.dropzone > span:not(.dropzone__icon) { color: var(--muted); font-size: 12px; margin-bottom: 8px; }
.selected-file { width: 100%; display: flex; align-items: center; gap: 11px; padding: 12px; border: 1px solid var(--line); border-radius: 10px; background: white; text-align: left; }
.selected-file__icon { width: 36px; height: 36px; display: grid; place-items: center; flex-shrink: 0; border-radius: 9px; background: var(--teal-soft); color: var(--teal); font-size: 19px; }
.selected-file > div { min-width: 0; flex: 1; }
.selected-file strong { display: block; overflow: hidden; color: var(--ink); font-size: 13px; text-overflow: ellipsis; white-space: nowrap; }
.selected-file span:not(.selected-file__icon) { display: block; color: var(--muted); font-size: 12px; }
.selected-file__check { color: #198166; }
.upload-error { margin: 10px 0 0; color: #a13f28; font-size: 12px; overflow-wrap: anywhere; }
.upload-progress { margin-top: 16px; }
.upload-progress > div { display: flex; justify-content: space-between; margin-bottom: 6px; font-size: 12px; }
.upload-progress small { color: var(--muted); font-size: 11px; }
.mock-uploading { margin: 12px 0 0; color: var(--muted); font-size: 12px; text-align: center; }
.submit-button { width: 100%; margin-top: 14px; }
.submit-button.is-disabled { background: #cddadb !important; border-color: #cddadb !important; color: #fff !important; }
.upload-rules { display: flex; flex-wrap: wrap; justify-content: center; gap: 5px; margin: 14px 0 0; padding: 0; list-style: none; }
.upload-rules li { padding: 2px 7px; border-radius: 5px; background: #f2f6f6; color: var(--muted); font-size: 11px; }
@media (max-width: 850px) { .upload-panel { padding: 20px; } }
</style>

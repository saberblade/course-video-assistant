import type { VideoStatus } from "@/types";

export const MAX_FILE_SIZE = 200 * 1024 * 1024;
export const MAX_QUESTION_LENGTH = 300;

export function formatTime(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds < 0) return "--:--";
  const wholeSeconds = Math.floor(seconds);
  const minutes = Math.floor(wholeSeconds / 60);
  const remainder = wholeSeconds % 60;
  return `${String(minutes).padStart(2, "0")}:${String(remainder).padStart(2, "0")}`;
}

export function formatDuration(seconds: number): string {
  if (!seconds) return "待检测";
  return formatTime(seconds);
}

export function formatBytes(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes < 0) return "未知大小";
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

export function formatDate(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "时间未知";
  return new Intl.DateTimeFormat("zh-CN", {
    timeZone: "Asia/Shanghai",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(date);
}

export function elapsedText(video: { status: VideoStatus; elapsed_sec: number; created_at: string; updated_at: string; attempt: number }): string {
  if (video.status === "queued") {
    const waitingSince = video.attempt > 1 ? video.updated_at : video.created_at;
    const seconds = Math.max(0, Math.floor((Date.now() - new Date(waitingSince).getTime()) / 1000));
    return `已排队 ${formatTime(seconds)}`;
  }
  return `已处理 ${formatTime(video.elapsed_sec)}`;
}

export const statusMeta: Record<VideoStatus, { label: string; description: string }> = {
  queued: { label: "等待处理", description: "视频已进入队列，即将开始转写" },
  transcribing: { label: "正在转写", description: "正在识别课程音轨并整理原文" },
  indexing: { label: "正在整理", description: "正在生成章节提要与检索索引" },
  ready: { label: "可以复习", description: "转写、章节与问答已准备就绪" },
  failed: { label: "处理失败", description: "本次处理未完成，请查看原因" },
};

export function validateFile(file: File): string {
  if (!file.name.toLowerCase().endsWith(".mp4")) return "请选择 MP4 格式的视频文件";
  if (file.size === 0) return "文件内容为空，请重新选择";
  if (file.size > MAX_FILE_SIZE) return "视频不能超过 200 MiB，请选择较小的文件";
  return "";
}

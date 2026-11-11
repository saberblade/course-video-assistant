import { ref, watch } from "vue";
import { isMock } from "@/api";
import { sessionState } from "@/stores/session";
import type { Chapter, Video } from "@/types";

export interface ReviewRecord {
  key: string;
  videoId: string;
  videoTitle: string;
  attempt: number;
  chapterId: string;
  start: number;
  end: number;
  text: string;
  reviewed: boolean;
  saved: boolean;
  resolved: boolean;
  note: string;
  updatedAt: string;
}

const storageKey = `course-review:review-records:v1:${isMock ? "mock" : "real"}`;
const storageError = ref("");
function read(): ReviewRecord[] {
  // Anonymous browser records are retained on disk, never assigned to a new account.
  if (!isMock) return [];
  try {
    const raw = localStorage.getItem(storageKey);
    if (!raw) return [];
    const value: unknown = JSON.parse(raw);
    if (!Array.isArray(value)) throw new Error("invalid records");
    return value.filter((r): r is ReviewRecord => Boolean(r && typeof r === "object"
      && typeof r.key === "string" && typeof r.videoId === "string" && typeof r.videoTitle === "string"
      && typeof r.chapterId === "string" && Number.isInteger(r.attempt) && r.attempt >= 1
      && Number.isFinite(r.start) && r.start >= 0 && Number.isFinite(r.end) && r.end > r.start
      && typeof r.text === "string" && typeof r.note === "string" && typeof r.updatedAt === "string"
      && typeof r.reviewed === "boolean" && typeof r.saved === "boolean" && typeof r.resolved === "boolean"));
  } catch {
    storageError.value = "无法读取浏览器复习记录。课程内容仍可使用，新标记会尝试重新保存。";
    return [];
  }
}
const records = ref<ReviewRecord[]>(read());
const canSave = isMock; // Enable real saves only when DB-03 endpoints are delivered and integrated.
watch(sessionState.revision, () => { if (!isMock) records.value = []; }, { flush: "sync" });
function persist() {
  if (!isMock) return;
  try {
    localStorage.setItem(storageKey, JSON.stringify(records.value));
    storageError.value = "";
  } catch {
    storageError.value = "浏览器暂时无法保存记录，本次标记仅在当前页面有效。请检查浏览器存储设置。";
  }
}
function keyFor(video: Video, chapter: Chapter) {
  return `${video.id}:${video.attempt}:${chapter.id}`;
}
function find(video: Video, chapter: Chapter) {
  return records.value.find(r => r.key === keyFor(video, chapter));
}
function update(video: Video, chapter: Chapter, changes: Partial<Pick<ReviewRecord, "reviewed" | "saved" | "resolved" | "note">>) {
  if (!canSave) return;
  const previous = find(video, chapter);
  const next: ReviewRecord = {
    key: keyFor(video, chapter), videoId: video.id, videoTitle: video.title,
    attempt: video.attempt, chapterId: chapter.id, start: chapter.start_sec, end: chapter.end_sec,
    text: chapter.text, reviewed: false, saved: false, resolved: false, note: "",
    ...previous, ...changes, updatedAt: new Date().toISOString(),
  };
  records.value = [...records.value.filter(r => r.key !== next.key), next];
  persist();
}
function edit(key: string, changes: Partial<Pick<ReviewRecord, "note" | "resolved">>) {
  if (!canSave) return;
  records.value = records.value.map(r => r.key === key ? { ...r, ...changes, updatedAt: new Date().toISOString() } : r);
  persist();
}
function remove(key: string) {
  if (!canSave) return;
  // 移出清单保留独立的手动复习标记。
  records.value = records.value.map(r => r.key === key ? { ...r, saved: false, resolved: false, note: "", updatedAt: new Date().toISOString() } : r);
  persist();
}
function onStorage(event: StorageEvent) {
  if (event.key === storageKey || event.key === null) records.value = read();
}
window.addEventListener("storage", onStorage);
if (import.meta.hot) import.meta.hot.dispose(() => window.removeEventListener("storage", onStorage));

export function useReviewRecords() {
  return { records, storageError, canSave, find, update, edit, remove };
}

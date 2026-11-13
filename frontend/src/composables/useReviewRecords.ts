import { computed, ref, watch } from "vue";
import { api, isMock } from "@/api";
import { toApiError } from "@/api/http";
import { sessionState } from "@/stores/session";
import type { Chapter, ReviewRecordPayload, Video } from "@/types";

/** 页面展示用的复习记录：服务端字段 + 便于本地索引的 key。 */
export interface ReviewRecord {
  key: string;
  id: string;
  version: number;
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
  isStale: boolean;
}

export type SaveState = "idle" | "saving" | "saved" | "failed";

const records = ref<ReviewRecord[]>([]);
const saveState = ref<SaveState>("idle");
const storageError = ref("");
const loading = ref(false);
const loaded = ref(false);

function toRecord(payload: ReviewRecordPayload): ReviewRecord {
  return {
    key: `${payload.video_id}:${payload.attempt}:${payload.chapter_id}`,
    id: payload.id,
    version: payload.version,
    videoId: payload.video_id,
    videoTitle: payload.video_title,
    attempt: payload.attempt,
    chapterId: payload.chapter_id,
    start: payload.start_sec,
    end: payload.end_sec,
    text: payload.text,
    reviewed: payload.reviewed,
    saved: payload.saved,
    resolved: payload.resolved,
    note: payload.note,
    updatedAt: payload.updated_at,
    isStale: payload.is_stale,
  };
}

function merge(incoming: ReviewRecord[]) {
  const byKey = new Map(records.value.map(item => [item.key, item]));
  for (const item of incoming) byKey.set(item.key, item);
  records.value = [...byKey.values()];
}

async function refresh(): Promise<void> {
  const revision = sessionState.revision.value;
  if (isMock) {
    loading.value = true;
    try {
      const result = await api.listMyReviewRecords("all", 100, 0);
      records.value = result.items.map(toRecord);
      loaded.value = true;
    } catch (error) {
      storageError.value = toApiError(error).message;
    } finally {
      loading.value = false;
    }
    return;
  }
  if (!sessionState.user.value) {
    records.value = [];
    loaded.value = false;
    return;
  }
  loading.value = true;
  try {
    const collected: ReviewRecord[] = [];
    let offset = 0;
    // 清单按 updated_at 倒序，分页拉满，避免超过一页后旧记录丢失。
    for (let guard = 0; guard < 20; guard += 1) {
      const page = await api.listMyReviewRecords("all", 100, offset);
      collected.push(...page.items.map(toRecord));
      offset += page.items.length;
      if (!page.items.length || offset >= page.total) break;
    }
    if (revision !== sessionState.revision.value) return;
    records.value = collected;
    loaded.value = true;
    storageError.value = "";
  } catch (error) {
    if (revision !== sessionState.revision.value) return;
    storageError.value = `无法读取复习记录：${toApiError(error).message}`;
  } finally {
    if (revision === sessionState.revision.value) loading.value = false;
  }
}

function keyFor(video: Video, chapter: Chapter) {
  return `${video.id}:${video.attempt}:${chapter.id}`;
}

function find(video: Video, chapter: Chapter) {
  return records.value.find(record => record.key === keyFor(video, chapter));
}

/** 冲突时重新读取服务端，并把提示留给页面显示。 */
async function recoverFromConflict(message: string) {
  const revision = sessionState.revision.value;
  await refresh();
  if (revision !== sessionState.revision.value) return;
  saveState.value = "failed";
  storageError.value = message;
}

async function update(
  video: Video,
  chapter: Chapter,
  changes: Partial<Pick<ReviewRecord, "reviewed" | "saved" | "resolved" | "note">>,
) {
  const revision = sessionState.revision.value;
  const previous = find(video, chapter);
  const expectedVersion = previous?.version ?? 0;
  const optimistic: ReviewRecord = {
    key: keyFor(video, chapter),
    id: previous?.id ?? "",
    version: expectedVersion,
    videoId: video.id,
    videoTitle: video.title,
    attempt: video.attempt,
    chapterId: chapter.id,
    start: chapter.start_sec,
    end: chapter.end_sec,
    text: chapter.text,
    reviewed: false,
    saved: false,
    resolved: false,
    note: "",
    updatedAt: new Date().toISOString(),
    isStale: false,
    ...previous,
    ...changes,
  };
  merge([optimistic]);
  saveState.value = "saving";
  try {
    const payload = await api.patchChapterReview(video.id, chapter.id, {
      attempt: video.attempt,
      expected_version: expectedVersion,
      ...changes,
    });
    if (revision !== sessionState.revision.value) return;
    merge([toRecord(payload)]);
    saveState.value = "saved";
    storageError.value = "";
    return true;
  } catch (error) {
    if (revision !== sessionState.revision.value) return;
    const apiError = toApiError(error);
    if (apiError.code === "VERSION_CONFLICT" || apiError.code === "STALE_ATTEMPT") {
      await recoverFromConflict("这个章节已在另一个窗口更新，已为你刷新最新状态，请重新标记。");
      return;
    }
    // 失败就回滚乐观更新，不能显示成已保存。
    if (previous) {
      merge([previous]);
    } else {
      records.value = records.value.filter(record => record.key !== optimistic.key);
    }
    saveState.value = "failed";
    storageError.value = `保存未完成：${apiError.message}`;
  }
  return false;
}

function recordByKey(key: string) {
  return records.value.find(record => record.key === key);
}

async function edit(key: string, changes: Partial<Pick<ReviewRecord, "note" | "resolved" | "saved" | "reviewed">>) {
  const revision = sessionState.revision.value;
  const target = recordByKey(key);
  if (!target || !target.id) {
    storageError.value = "这条记录还没有保存到服务器，请重新标记后再编辑。";
    saveState.value = "failed";
    return;
  }
  const snapshot = { ...target };
  merge([{ ...target, ...changes, updatedAt: new Date().toISOString() }]);
  saveState.value = "saving";
  try {
    const payload = await api.patchMyReviewRecord(target.id, {
      expected_version: target.version,
      ...changes,
    });
    if (revision !== sessionState.revision.value) return;
    merge([toRecord(payload)]);
    saveState.value = "saved";
    storageError.value = "";
    return true;
  } catch (error) {
    if (revision !== sessionState.revision.value) return;
    const apiError = toApiError(error);
    if (apiError.code === "VERSION_CONFLICT") {
      await recoverFromConflict("这条记录已在另一个窗口更新，已为你刷新最新状态。");
      return;
    }
    merge([snapshot]);
    saveState.value = "failed";
    storageError.value = `保存未完成：${apiError.message}`;
  }
  return false;
}

async function remove(key: string) {
  // 移出清单：保留独立 reviewed 标记，只清 saved/resolved/note。
  await edit(key, { saved: false, resolved: false, note: "" });
}

watch(sessionState.revision, () => {
  records.value = [];
  loaded.value = false;
  loading.value = false;
  storageError.value = "";
  saveState.value = "idle";
  if (sessionState.user.value) void refresh();
}, { flush: "sync" });

export function useReviewRecords() {
  return {
    records,
    storageError,
    canSave: computed(() => Boolean(sessionState.user.value)),
    saveState,
    loading,
    loaded,
    refresh,
    find,
    update,
    edit,
    remove,
  };
}

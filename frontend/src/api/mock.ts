import { ApiError } from "./http";
import type {
  ChapterReviewInput,
  MockAnswerMode,
  PlaybackProgress,
  ProgressSaveInput,
  QuestionHistoryResponse,
  QuestionResult,
  ReviewEditInput,
  ReviewListResponse,
  ReviewRecordPayload,
  Summary,
  TranscriptResponse,
  TranscriptSegment,
  Video,
  VideoListResponse,
  VideoStatus,
} from "@/types";

export const KNOWLEDGE_MAP_SAMPLE_ID = "43b4b091-630e-4819-8f56-f20b9120c001";
const processingId = "43b4b091-630e-4819-8f56-f20b9120c002";
const failedId = "43b4b091-630e-4819-8f56-f20b9120c003";

const baseVideo = {
  processing_mode: "audio_only" as const,
  duration_sec: 180,
  size_bytes: 15_728_640,
  started_at: "2026-11-05T02:00:01Z",
  finished_at: "2026-11-05T02:02:01Z",
  elapsed_sec: 120,
  attempt: 1,
  error: null,
};

let videos: Video[] = [
  {
    ...baseVideo,
    id: processingId,
    title: "机器学习第三章_演示处理中",
    status: "transcribing",
    created_at: "2026-11-05T02:05:00Z",
    updated_at: "2026-11-05T02:05:01Z",
    started_at: "2026-11-05T02:05:01Z",
    finished_at: null,
    elapsed_sec: 45,
  },
  {
    ...baseVideo,
    id: KNOWLEDGE_MAP_SAMPLE_ID,
    title: "分类模型评估_虚构联调样例",
    status: "ready",
    created_at: "2026-11-05T02:00:00Z",
    updated_at: "2026-11-05T02:02:01Z",
  },
  {
    ...baseVideo,
    id: failedId,
    title: "模型评估补充课_演示失败态",
    status: "failed",
    created_at: "2026-11-05T01:40:00Z",
    updated_at: "2026-11-05T01:42:01Z",
    error: { code: "PROCESS_INTERRUPTED", message: "上次处理因服务重启中断，可重试", retryable: true },
  },
];

const segments: TranscriptSegment[] = [
  { id: "7c388118-4875-4125-9383-40513670c000", start_sec: 12.4, end_sec: 22, text: "今天我们来学习分类模型的评估方法，重点理解精确率、召回率和 F1 值。" },
  { id: "7c388118-4875-4125-9383-40513670c001", start_sec: 32.5, end_sec: 39, text: "精确率等于真正例除以真正例与假正例之和。" },
  { id: "7c388118-4875-4125-9383-40513670c002", start_sec: 62, end_sec: 70, text: "召回率等于真正例除以真正例与假反例之和。" },
  { id: "7c388118-4875-4125-9383-40513670c003", start_sec: 84, end_sec: 96, text: "精确率关注预测为正的样本中有多少是真的，召回率关注真实为正的样本中有多少被找出来。" },
  { id: "7c388118-4875-4125-9383-40513670c004", start_sec: 128, end_sec: 139, text: "F1 值是精确率和召回率的调和平均数，用于综合衡量这两个指标。" },
  { id: "7c388118-4875-4125-9383-40513670c005", start_sec: 145, end_sec: 157, text: "实际应用中，要根据业务代价决定更关注漏报还是误报，而不是只看准确率。" },
];

const transcript: TranscriptResponse = { video_id: KNOWLEDGE_MAP_SAMPLE_ID, segments };
const summary: Summary = {
  video_id: KNOWLEDGE_MAP_SAMPLE_ID,
  mode: "extractive",
  chapters: [
    {
      id: "a738bafe-7487-47c5-8c3d-45226d90c001",
      start_sec: 0,
      end_sec: 60,
      title: "00:00 章节提要",
      text: "今天我们来学习分类模型的评估方法，重点理解精确率、召回率和 F1 值。精确率等于真正例除以真正例与假正例之和。",
      segment_ids: [segments[0].id, segments[1].id],
    },
    {
      id: "a738bafe-7487-47c5-8c3d-45226d90c002",
      start_sec: 60,
      end_sec: 120,
      title: "01:00 章节提要",
      text: "召回率等于真正例除以真正例与假反例之和。精确率关注预测为正的样本中有多少是真的，召回率关注真实为正的样本中有多少被找出来。",
      segment_ids: [segments[2].id, segments[3].id],
    },
    {
      id: "a738bafe-7487-47c5-8c3d-45226d90c003",
      start_sec: 120,
      end_sec: 180,
      title: "02:00 章节提要",
      text: "F1 值是精确率和召回率的调和平均数，用于综合衡量这两个指标。实际应用中，要根据业务代价决定更关注漏报还是误报。",
      segment_ids: [segments[4].id, segments[5].id],
    },
  ],
};

let answerMode: MockAnswerMode = "answered";
const wait = (ms = 360) => new Promise((resolve) => window.setTimeout(resolve, ms));
const clone = <T>(value: T): T => structuredClone(value);
const findVideo = (id: string) => videos.find((video) => video.id === id);

function requireVideo(id: string): Video {
  const video = findVideo(id);
  if (!video) throw new ApiError({ code: "VIDEO_NOT_FOUND", message: "视频不存在或已删除", status: 404 });
  return video;
}

function requireReady(id: string): Video {
  const video = requireVideo(id);
  if (video.status !== "ready") {
    throw new ApiError({ code: "VIDEO_NOT_READY", message: "视频尚未处理完成，请稍后再试", status: 409 });
  }
  return video;
}

export function setMockAnswerMode(mode: MockAnswerMode): void {
  answerMode = mode;
}

// 演示模式的本地学习档案。真实模式一律走服务端接口。
const mockProgress = new Map<string, PlaybackProgress>();
let mockRecords: ReviewRecordPayload[] = [];
let mockQuestions: QuestionResult[] = [];

function recordKey(videoId: string, attempt: number, chapterId: string): string {
  return `${videoId}:${attempt}:${chapterId}`;
}

function upsertRecord(next: ReviewRecordPayload): ReviewRecordPayload {
  mockRecords = [next, ...mockRecords.filter(item => item.id !== next.id)];
  return next;
}

export const mockApi = {
  async listVideos(limit = 20, offset = 0): Promise<VideoListResponse> {
    await wait();
    const sorted = [...videos].sort((a, b) => b.created_at.localeCompare(a.created_at));
    return { items: clone(sorted.slice(offset, offset + limit)), total: videos.length, limit, offset };
  },

  async getVideo(id: string): Promise<Video> {
    await wait(220);
    return clone(requireVideo(id));
  },

  async uploadVideo(file: File): Promise<Video> {
    await wait(650);
    const now = new Date().toISOString();
    const video: Video = {
      id: crypto.randomUUID(),
      title: file.name.replace(/\.mp4$/i, ""),
      status: "queued",
      processing_mode: "audio_only",
      duration_sec: 180,
      size_bytes: file.size,
      created_at: now,
      updated_at: now,
      started_at: null,
      finished_at: null,
      elapsed_sec: 0,
      attempt: 1,
      error: null,
    };
    videos = [video, ...videos];
    return clone(video);
  },

  async getTranscript(id: string): Promise<TranscriptResponse> {
    await wait();
    requireReady(id);
    return clone({ ...transcript, video_id: id });
  },

  async getSummary(id: string): Promise<Summary> {
    await wait();
    requireReady(id);
    return clone({ ...summary, video_id: id });
  },

  async askQuestion(id: string, question: string): Promise<QuestionResult> {
    await wait(900);
    requireReady(id);
    const isPrecision = question.includes("精确率");
    const citation = clone(segments[isPrecision ? 1 : 2]);
    const result: QuestionResult = {
      id: crypto.randomUUID(),
      video_id: id,
      question,
      answer_status: answerMode,
      mode: answerMode === "answered" ? "generative" : "extractive",
      answer:
        answerMode === "not_found"
          ? "当前视频中未找到足够依据，请换一种问法或回看课程。"
          : answerMode === "degraded"
            ? "生成服务暂不可用，以下是检索到的课程原文。"
            : isPrecision
              ? "精确率是真正例数量除以真正例与假正例之和，用于衡量预测为正的样本中有多少是真的。"
              : "召回率是真正例数量除以真正例与假反例之和，用于衡量真实为正的样本中有多少被成功找出。",
      citations:
        answerMode === "not_found"
          ? []
          : [{ segment_id: citation.id, start_sec: citation.start_sec, end_sec: citation.end_sec, text: citation.text }],
      created_at: new Date().toISOString(),
      latency_ms: answerMode === "degraded" ? 25_100 : 900,
    };
    mockQuestions = [result, ...mockQuestions];
    return clone(result);
  },

  async retryVideo(id: string): Promise<Video> {
    await wait();
    const video = requireVideo(id);
    if (video.status !== "failed" || !video.error?.retryable) {
      throw new ApiError({ code: "RETRY_NOT_ALLOWED", message: "当前任务不允许重试", status: 409 });
    }
    const now = new Date().toISOString();
    Object.assign(video, {
      status: "queued" as VideoStatus,
      updated_at: now,
      started_at: null,
      finished_at: null,
      elapsed_sec: 0,
      attempt: video.attempt + 1,
      error: null,
    });
    return clone(video);
  },

  async deleteVideo(id: string): Promise<void> {
    await wait();
    const video = requireVideo(id);
    if (!(["ready", "failed"] as VideoStatus[]).includes(video.status)) {
      throw new ApiError({ code: "VIDEO_BUSY", message: "视频正在处理或回答问题，暂时不能删除", status: 409 });
    }
    videos = videos.filter((item) => item.id !== id);
  },

  async setVideoStatus(id: string, status: VideoStatus): Promise<Video> {
    await wait(120);
    const video = requireVideo(id);
    video.status = status;
    video.updated_at = new Date().toISOString();
    video.error = status === "failed"
      ? { code: "PROCESS_INTERRUPTED", message: "上次处理因服务重启中断，可重试", retryable: true }
      : null;
    video.elapsed_sec = status === "queued" ? 0 : status === "ready" || status === "failed" ? 120 : 45;
    return clone(video);
  },

  async listQuestions(id: string, limit = 20, offset = 0): Promise<QuestionHistoryResponse> {
    await wait(160);
    requireVideo(id);
    const items = mockQuestions.filter(item => item.video_id === id);
    return { items: clone(items.slice(offset, offset + limit)), total: items.length, limit, offset };
  },

  async getProgress(id: string): Promise<PlaybackProgress> {
    await wait(120);
    const video = requireVideo(id);
    return clone(
      mockProgress.get(recordKey(id, video.attempt, "")) ?? {
        video_id: id,
        attempt: video.attempt,
        position_sec: 0,
        furthest_sec: 0,
        version: 0,
        updated_at: "",
        saved: false,
      },
    );
  },

  async saveProgress(id: string, body: ProgressSaveInput): Promise<PlaybackProgress> {
    await wait(140);
    const video = requireVideo(id);
    if (body.attempt !== video.attempt) {
      throw new ApiError({ code: "STALE_ATTEMPT", message: "视频已重新处理，请刷新后再继续", status: 409 });
    }
    const key = recordKey(id, video.attempt, "");
    const current = mockProgress.get(key);
    const currentVersion = current?.version ?? 0;
    if (body.expected_version !== currentVersion) {
      throw new ApiError({ code: "VERSION_CONFLICT", message: "进度已在另一个窗口更新，请先刷新", status: 409 });
    }
    const next: PlaybackProgress = {
      video_id: id,
      attempt: video.attempt,
      position_sec: body.position_sec,
      furthest_sec: Math.max(current?.furthest_sec ?? 0, body.position_sec),
      version: currentVersion + 1,
      updated_at: new Date().toISOString(),
      saved: true,
    };
    mockProgress.set(key, next);
    return clone(next);
  },

  async listReviewRecords(id: string, limit = 200, offset = 0): Promise<ReviewListResponse> {
    await wait(150);
    const video = requireVideo(id);
    const items = mockRecords.filter(item => item.video_id === id && item.attempt === video.attempt);
    return { items: clone(items.slice(offset, offset + limit)), total: items.length, limit, offset };
  },

  async patchChapterReview(id: string, chapterId: string, body: ChapterReviewInput): Promise<ReviewRecordPayload> {
    await wait(180);
    const video = requireVideo(id);
    if (body.attempt !== video.attempt) {
      throw new ApiError({ code: "STALE_ATTEMPT", message: "视频已重新处理，请刷新后再标记", status: 409 });
    }
    const chapter = summary.chapters.find(item => item.id === chapterId);
    if (!chapter) throw new ApiError({ code: "CHAPTER_NOT_FOUND", message: "章节不存在", status: 404 });
    const existing = mockRecords.find(item => item.video_id === id && item.attempt === video.attempt && item.chapter_id === chapterId);
    const version = existing?.version ?? 0;
    if (body.expected_version !== version) {
      throw new ApiError({ code: "VERSION_CONFLICT", message: "标记已在另一个窗口更新，请先刷新", status: 409 });
    }
    return clone(upsertRecord({
      id: existing?.id ?? crypto.randomUUID(),
      video_id: id,
      video_title: video.title,
      chapter_id: chapterId,
      attempt: video.attempt,
      start_sec: chapter.start_sec,
      end_sec: chapter.end_sec,
      text: chapter.text,
      reviewed: body.reviewed ?? existing?.reviewed ?? false,
      saved: body.saved ?? existing?.saved ?? false,
      resolved: body.resolved ?? existing?.resolved ?? false,
      note: body.note ?? existing?.note ?? "",
      version: version + 1,
      is_stale: false,
      updated_at: new Date().toISOString(),
    }));
  },

  async listMyReviewRecords(status: "open" | "resolved" | "all" = "all", limit = 100, offset = 0): Promise<ReviewListResponse> {
    await wait(150);
    const filtered = mockRecords.filter(item => {
      if (status === "open") return item.saved && !item.resolved;
      if (status === "resolved") return item.resolved;
      return item.saved || item.resolved || item.reviewed;
    });
    return { items: clone(filtered.slice(offset, offset + limit)), total: filtered.length, limit, offset };
  },

  async patchMyReviewRecord(recordId: string, body: ReviewEditInput): Promise<ReviewRecordPayload> {
    await wait(160);
    const existing = mockRecords.find(item => item.id === recordId);
    if (!existing) throw new ApiError({ code: "RECORD_NOT_FOUND", message: "记录不存在", status: 404 });
    if (body.expected_version !== existing.version) {
      throw new ApiError({ code: "VERSION_CONFLICT", message: "记录已在另一个窗口更新，请先刷新", status: 409 });
    }
    return clone(upsertRecord({
      ...existing,
      reviewed: body.reviewed ?? existing.reviewed,
      saved: body.saved ?? existing.saved,
      resolved: body.resolved ?? existing.resolved,
      note: body.note ?? existing.note,
      version: existing.version + 1,
      updated_at: new Date().toISOString(),
    }));
  },
};

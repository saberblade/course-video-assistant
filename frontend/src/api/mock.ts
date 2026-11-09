import { ApiError } from "./http";
import type {
  MockAnswerMode,
  QuestionResult,
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
    return result;
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
};

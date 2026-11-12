export type VideoStatus = "queued" | "transcribing" | "indexing" | "ready" | "failed";
export type AnswerStatus = "answered" | "not_found" | "degraded";
export type AnswerMode = "generative" | "extractive";
export type MockAnswerMode = "answered" | "not_found" | "degraded";

export interface VideoError {
  code: string;
  message: string;
  retryable: boolean;
}

export interface Video {
  id: string;
  title: string;
  status: VideoStatus;
  processing_mode: "audio_only";
  duration_sec: number;
  size_bytes: number;
  created_at: string;
  updated_at: string;
  started_at: string | null;
  finished_at: string | null;
  elapsed_sec: number;
  attempt: number;
  error: VideoError | null;
}

export interface VideoListResponse {
  items: Video[];
  total: number;
  limit: number;
  offset: number;
}

export interface TranscriptSegment {
  id: string;
  start_sec: number;
  end_sec: number;
  text: string;
}

export interface TranscriptResponse {
  video_id: string;
  segments: TranscriptSegment[];
}

export interface Chapter {
  id: string;
  start_sec: number;
  end_sec: number;
  title: string;
  text: string;
  segment_ids: string[];
}

export interface Summary {
  video_id: string;
  mode: "extractive";
  chapters: Chapter[];
}

export interface Citation {
  segment_id: string;
  start_sec: number;
  end_sec: number;
  text: string;
}

export interface QuestionResult {
  id: string;
  video_id: string;
  question: string;
  answer_status: AnswerStatus;
  mode: AnswerMode;
  answer: string;
  citations: Citation[];
  created_at: string;
  latency_ms: number;
  retrieval_mode?: string | null;
  retrieval_version?: string | null;
}

export interface QuestionHistoryResponse {
  items: QuestionResult[];
  total: number;
  limit: number;
  offset: number;
}

export interface PlaybackProgress {
  video_id: string;
  attempt: number;
  position_sec: number;
  furthest_sec: number;
  version: number;
  updated_at: string;
  saved: boolean;
}

export interface ProgressSaveInput {
  attempt: number;
  position_sec: number;
  expected_version: number;
}

export interface ReviewRecordPayload {
  id: string;
  video_id: string;
  video_title: string;
  chapter_id: string;
  attempt: number;
  start_sec: number;
  end_sec: number;
  text: string;
  reviewed: boolean;
  saved: boolean;
  resolved: boolean;
  note: string;
  version: number;
  is_stale: boolean;
  updated_at: string;
}

export interface ReviewListResponse {
  items: ReviewRecordPayload[];
  total: number;
  limit: number;
  offset: number;
}

export interface ReviewChangeSet {
  reviewed?: boolean;
  saved?: boolean;
  resolved?: boolean;
  note?: string;
}

export interface ChapterReviewInput extends ReviewChangeSet {
  attempt: number;
  expected_version: number;
}

export interface ReviewEditInput extends ReviewChangeSet {
  expected_version: number;
}

export interface ApiErrorBody {
  error: VideoError;
  request_id: string;
}

export interface UploadProgress {
  loaded: number;
  total: number;
}

export interface ApiErrorShape {
  message: string;
  code: string;
  requestId?: string;
  retryAfter?: number;
  status?: number;
}

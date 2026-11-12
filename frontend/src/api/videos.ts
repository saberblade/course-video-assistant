import { http } from "./http";
import type {
  ChapterReviewInput,
  PlaybackProgress,
  ProgressSaveInput,
  QuestionHistoryResponse,
  QuestionResult,
  ReviewEditInput,
  ReviewListResponse,
  ReviewRecordPayload,
  Summary,
  TranscriptResponse,
  UploadProgress,
  Video,
  VideoListResponse,
} from "@/types";

export const realApi = {
  async listVideos(limit = 20, offset = 0): Promise<VideoListResponse> {
    const response = await http.get<VideoListResponse>("/videos", { params: { limit, offset } });
    return response.data;
  },

  async getVideo(id: string): Promise<Video> {
    const response = await http.get<Video>(`/videos/${id}`);
    return response.data;
  },

  async uploadVideo(file: File, onProgress?: (progress: UploadProgress) => void): Promise<Video> {
    const form = new FormData();
    form.append("file", file);
    const response = await http.post<Video>("/videos", form, {
      onUploadProgress: (event) => {
        if (event.total) onProgress?.({ loaded: event.loaded, total: event.total });
      },
    });
    return response.data;
  },

  async getTranscript(id: string): Promise<TranscriptResponse> {
    const response = await http.get<TranscriptResponse>(`/videos/${id}/transcript`);
    return response.data;
  },

  async getSummary(id: string): Promise<Summary> {
    const response = await http.get<Summary>(`/videos/${id}/summary`);
    return response.data;
  },

  async askQuestion(id: string, question: string): Promise<QuestionResult> {
    const response = await http.post<QuestionResult>(`/videos/${id}/questions`, { question });
    return response.data;
  },

  async retryVideo(id: string): Promise<Video> {
    const response = await http.post<Video>(`/videos/${id}/retry`);
    return response.data;
  },

  async deleteVideo(id: string): Promise<void> {
    await http.delete(`/videos/${id}`);
  },

  async listQuestions(id: string, limit = 20, offset = 0): Promise<QuestionHistoryResponse> {
    const response = await http.get<QuestionHistoryResponse>(`/videos/${id}/questions`, { params: { limit, offset } });
    return response.data;
  },

  async getProgress(id: string): Promise<PlaybackProgress> {
    const response = await http.get<PlaybackProgress>(`/videos/${id}/progress`);
    return response.data;
  },

  async saveProgress(id: string, body: ProgressSaveInput): Promise<PlaybackProgress> {
    const response = await http.put<PlaybackProgress>(`/videos/${id}/progress`, body);
    return response.data;
  },

  async listReviewRecords(id: string, limit = 200, offset = 0): Promise<ReviewListResponse> {
    const response = await http.get<ReviewListResponse>(`/videos/${id}/review-records`, { params: { limit, offset } });
    return response.data;
  },

  async patchChapterReview(id: string, chapterId: string, body: ChapterReviewInput): Promise<ReviewRecordPayload> {
    const response = await http.patch<ReviewRecordPayload>(
      `/videos/${id}/chapters/${chapterId}/review`,
      body,
    );
    return response.data;
  },

  async listMyReviewRecords(status: "open" | "resolved" | "all" = "all", limit = 100, offset = 0): Promise<ReviewListResponse> {
    const response = await http.get<ReviewListResponse>("/me/review-records", { params: { status, limit, offset } });
    return response.data;
  },

  async patchMyReviewRecord(recordId: string, body: ReviewEditInput): Promise<ReviewRecordPayload> {
    const response = await http.patch<ReviewRecordPayload>(`/me/review-records/${recordId}`, body);
    return response.data;
  },
};

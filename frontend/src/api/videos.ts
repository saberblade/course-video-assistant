import { http } from "./http";
import type {
  QuestionResult,
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
};

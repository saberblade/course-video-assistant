import { ApiError, http } from "./http";
import { sessionState } from "@/stores/session";

export interface AssistantMessage {
  role: "user" | "assistant";
  content: string;
}

export const assistantUsesApi = import.meta.env.VITE_ASSISTANT_USE_API === "true";
export interface AssistantReply { answer: string; mode: "generative" | "guide" }

const guide = [
  {
    topic: /上传失败|无法上传|不能上传|处理失败|报错|超时/,
    answer: "先核对文件格式、大小、时长和音轨。上传后可以在「我的课程」打开视频，查看处理失败的原因。页面提供「重新处理」时，可以用原文件再试一次。",
  },
  {
    topic: /上传|格式|大小|时长|视频限制|mp4|200m|20分钟/i,
    answer: "在知识云台打开「我的课程」，选择或拖入 MP4 后点「开始处理」。视频须使用 H.264 编码和 AAC 音轨，最多 200 MiB、20 分钟，并包含清晰中文讲课音轨。",
  },
  {
    topic: /薄弱|预警|掌握度|学习分析|复习进度|待复习|已解决|备注|标记/,
    answer: "复习记录和待复习清单暂不可用。你可以先在课程知识导航中查找章节、回看讲解，或打开课程的「向课程提问」核对原文。",
  },
  {
    topic: /知识地图|知识导航|知识点|地图怎么/,
    answer: "「课程知识导航」按已处理视频的真实章节组织内容。选择视频后，可以搜索章节、核对来源原文、回看讲解，或把想再看的章节加入待复习清单。",
  },
  {
    topic: /进度|处理状态|转写多久|排队|转写中|处理中/,
    answer: "在「我的课程」打开已上传的视频即可看进度。课程依次进入排队、转写和整理，显示「可以复习」后就能查看原文与章节提要。",
  },
  {
    topic: /提问|问答|引用|定位|回看|章节|提要|转写/,
    answer: "从「我的课程」打开可复习的视频，再选「章节提要」或「向课程提问」。课程问答只依据当前视频的转写。点击回答的引用会跳到对应时间并暂停，方便核对原文。",
  },
  {
    topic: /演示|模拟|真实接口|mock/i,
    answer: "上传课程后，可以在「我的课程」查看处理进度。显示「可以复习」后，打开课程即可查看章节提要、原文转写，并围绕当前课程提问。",
  },
  {
    topic: /课迹|介绍|什么项目|有什么用|能做什么|怎么用|你是谁|你好/,
    answer: "课迹是一个课程视频复习助手。上传中文录课后，你可以按时间读章节提要、查转写或围绕课程提问，再用引用回到老师讲解的片段。我负责介绍项目和指引站内操作。",
  },
];

export async function askAssistant(messages: AssistantMessage[]): Promise<AssistantReply> {
  if (!assistantUsesApi || !sessionState.user.value) {
    const question = messages.at(-1)?.content.replace(/\s+/g, "") ?? "";
    return { mode: "guide", answer: guide.find(({ topic }) => topic.test(question))?.answer
      ?? "我目前能回答课迹的使用问题。可以问我怎么上传、怎么看处理进度，或者怎么用引用回看。想问课程里的知识，请登录后打开该课程的「向课程提问」。" };
  }

  const response = await http.post<AssistantReply>("/assistant/chat", { messages });
  const answer = response.data?.answer;
  if (typeof answer !== "string" || !answer.trim()) {
    throw new ApiError({ code: "ASSISTANT_INVALID_RESPONSE", message: "助教暂时没有返回有效回答，请重试" });
  }
  if (!["generative", "guide"].includes(response.data.mode)) throw new ApiError({ code: "ASSISTANT_INVALID_RESPONSE", message: "助教返回的回答状态无效，请重试" });
  return { answer: answer.trim(), mode: response.data.mode };
}

<script setup lang="ts">
import { computed, ref } from "vue";
import { ChatDotRound, MagicStick, Position, Search, Warning } from "@element-plus/icons-vue";
import { ElMessage } from "element-plus";
import { api, isMock } from "@/api";
import { toApiError } from "@/api/http";
import { setMockAnswerMode } from "@/api/mock";
import type { Citation, MockAnswerMode, QuestionResult } from "@/types";
import { formatTime, MAX_QUESTION_LENGTH } from "@/utils/format";

const props = defineProps<{ videoId: string }>();
const emit = defineEmits<{ seek: [seconds: number] }>();

const draft = ref("");
const asking = ref(false);
const inputError = ref("");
const results = ref<QuestionResult[]>([]);
const mockMode = ref<MockAnswerMode>("answered");
const trimmedCount = computed(() => draft.value.trim().length);

const suggestions = [
  "召回率怎样计算？",
  "精确率和召回率有什么区别？",
  "F1 值在什么场景下更有参考价值？",
];

function chooseSuggestion(question: string) {
  draft.value = question;
  inputError.value = "";
}

function changeMockMode(value: MockAnswerMode) {
  mockMode.value = value;
  setMockAnswerMode(value);
}

async function ask() {
  if (asking.value) return;
  const question = draft.value.trim();
  inputError.value = "";
  if (!question) {
    inputError.value = "请输入你的问题";
    return;
  }
  if (question.length > MAX_QUESTION_LENGTH) {
    inputError.value = `问题最多 ${MAX_QUESTION_LENGTH} 个字符，请精简后再提交`;
    return;
  }
  asking.value = true;
  try {
    const result = await api.askQuestion(props.videoId, question);
    results.value.unshift(result);
  } catch (error) {
    const apiError = toApiError(error);
    const suffix = apiError.retryAfter ? `（约 ${apiError.retryAfter} 秒后可重试）` : "";
    ElMessage.error(`${apiError.message}${suffix}`);
  } finally {
    asking.value = false;
  }
}

function statusLabel(result: QuestionResult): string {
  if (result.answer_status === "degraded") return "原文检索模式";
  if (result.answer_status === "not_found") return "未找到足够依据";
  return "基于原文生成";
}

function openCitation(citation: Citation) {
  emit("seek", citation.start_sec);
}
</script>

<template>
  <section class="panel question-panel" aria-labelledby="question-title">
    <div class="section-heading question-panel__heading">
      <div>
        <span class="section-kicker">ASK THE COURSE</span>
        <h3 id="question-title">向这段课程提问</h3>
        <p>仅依据当前视频原文，刷新后清空问答</p>
      </div>
      <span class="session-label"><ChatDotRound /> 本页会话</span>
    </div>

    <div v-if="isMock" class="mock-control">
      <span>演示回答类型</span>
      <el-select :model-value="mockMode" size="small" style="width: 132px" @change="changeMockMode">
        <el-option label="正常生成" value="answered" />
        <el-option label="未找到依据" value="not_found" />
        <el-option label="原文检索" value="degraded" />
      </el-select>
      <small>切换后仅影响下一次回答</small>
    </div>

    <div class="composer">
      <el-input
        v-model="draft"
        type="textarea"
        :rows="3"
        :maxlength="MAX_QUESTION_LENGTH + 1"
        :disabled="asking"
        placeholder="例如：召回率怎样计算？"
        aria-label="输入关于当前课程的问题"
        @keydown.ctrl.enter.prevent="ask"
      />
      <div class="composer__footer">
        <span class="counter" :class="{ 'counter--error': trimmedCount > MAX_QUESTION_LENGTH }">
          {{ trimmedCount }} / {{ MAX_QUESTION_LENGTH }}
        </span>
        <span class="shortcut">Ctrl + Enter 发送</span>
        <el-button type="primary" :loading="asking" :disabled="asking" @click="ask">
          <el-icon v-if="!asking"><Position /></el-icon>
          {{ asking ? "正在查找" : "提问" }}
        </el-button>
      </div>
      <p v-if="inputError" class="input-error" role="alert">{{ inputError }}</p>
    </div>

    <div v-if="!results.length && !asking" class="suggestions">
      <span>可以这样问</span>
      <button v-for="question in suggestions" :key="question" type="button" @click="chooseSuggestion(question)">
        {{ question }}
      </button>
    </div>

    <div class="results" role="log" aria-live="polite" aria-label="当前页面的问答结果">
      <div v-if="asking" class="answer-loading">
        <span class="answer-loading__icon"><Search /></span>
        <div><strong>正在检索课程原文…</strong><span>回答只依据本视频的转写内容</span></div>
      </div>

      <article v-for="result in results" :key="result.id" class="qa-item">
        <div class="question-bubble"><span>你问</span><p>{{ result.question }}</p></div>
        <div class="answer-card" :class="`answer-card--${result.answer_status}`">
          <div class="answer-card__status">
            <span>
              <el-icon v-if="result.answer_status === 'answered'"><MagicStick /></el-icon>
              <el-icon v-else><Warning /></el-icon>
              {{ statusLabel(result) }}
            </span>
            <span v-if="result.answer_status === 'degraded'" class="mode-tag">未生成综合回答</span>
          </div>
          <p class="answer-copy">{{ result.answer }}</p>
          <p v-if="result.answer_status === 'answered'" class="answer-hint">
            根据本视频转写生成，请点击下方引用核对原文
          </p>
          <p v-else-if="result.answer_status === 'degraded'" class="answer-hint">
            生成服务暂不可用，以下是检索到的真实课程原文。可稍后重新提问。
          </p>
          <p v-else class="answer-hint">
            当前问题在视频中没有足够原文依据。可以换一种问法，或查看章节提要。
          </p>

          <div v-if="result.citations.length" class="citations">
            <span class="citations__label">原文依据</span>
            <button
              v-for="citation in result.citations"
              :key="citation.segment_id"
              type="button"
              class="citation"
              @click="openCitation(citation)"
            >
              <span class="citation__top">
                <span class="time-text">{{ formatTime(citation.start_sec) }}</span>
                <span>定位到此处 <span aria-hidden="true">→</span></span>
              </span>
              <span class="citation__text">{{ citation.text }}</span>
            </button>
          </div>
          <p class="answer-meta">
            {{ result.mode === "generative" ? "生成式回答" : "提取式原文结果" }}
            <span>·</span>
            本次响应 {{ (result.latency_ms / 1000).toFixed(1) }} 秒
          </p>
        </div>
      </article>
    </div>
  </section>
</template>

<style scoped>
.question-panel { padding: 22px; min-width: 0; }
.question-panel__heading { align-items: flex-start; }
.session-label { display: inline-flex; align-items: center; gap: 4px; flex-shrink: 0; color: #789095; font-size: 11px; }
.session-label svg { width: 12px; }
.mock-control { display: flex; align-items: center; gap: 8px; margin-top: 14px; padding: 7px 9px; border-radius: 7px; background: #fff9ed; color: #806733; font-size: 12px; }
.mock-control small { margin-left: auto; color: #a08b60; font-size: 11px; }
.suggestions { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; margin-top: 17px; }
.suggestions > span { color: #84979c; font-size: 11px; margin-right: 2px; }
.suggestions button { padding: 4px 9px; border: 1px solid #e0e8e9; border-radius: 99px; background: white; color: #61777e; font-size: 11px; cursor: pointer; transition: 0.15s ease; }
.suggestions button:hover { border-color: #a7c8c5; color: var(--teal); background: #f7fbfa; }
.composer { margin-top: 15px; }
.composer__footer { display: flex; align-items: center; gap: 10px; margin-top: 8px; }
.counter { color: #8b9ba0; font-family: Consolas, monospace; font-size: 11px; }
.counter--error { color: #a03e26; }
.shortcut { margin-left: auto; color: #a0afb2; font-size: 11px; }
.input-error { margin: 5px 0 0; color: #a03e26; font-size: 12px; }
.results { margin-top: 20px; }
.qa-item + .qa-item { margin-top: 22px; padding-top: 22px; border-top: 1px dashed #e2eaeb; }
.question-bubble { display: flex; align-items: flex-start; gap: 8px; margin-bottom: 9px; }
.question-bubble > span { padding: 2px 6px; border-radius: 4px; background: #f0f4f4; color: #70868b; font-size: 10px; flex-shrink: 0; margin-top: 2px; }
.question-bubble p { margin: 0; color: #2b454d; font-size: 13px; font-weight: 600; line-height: 1.65; overflow-wrap: anywhere; }
.answer-card { padding: 13px 14px; border: 1px solid #dce9e5; border-radius: 9px; background: #fbfdfc; }
.answer-card--not_found { border-color: #eadfc9; background: #fffdf8; }
.answer-card--degraded { border-color: #ecdfc5; background: #fffbf3; }
.answer-card__status { display: flex; align-items: center; justify-content: space-between; gap: 10px; color: #24745f; font-size: 11px; font-weight: 650; }
.answer-card__status > span { display: inline-flex; align-items: center; gap: 4px; }
.answer-card__status svg { width: 12px; }
.answer-card--not_found .answer-card__status, .answer-card--degraded .answer-card__status { color: #8c6728; }
.mode-tag { padding: 2px 6px; border-radius: 4px; background: #f7edd8; color: #97702d !important; font-size: 10px; font-weight: 400; }
.answer-copy { margin: 9px 0 5px; color: #29454d; font-size: 13px; line-height: 1.85; overflow-wrap: anywhere; }
.answer-hint { margin: 0; color: #7e9297; font-size: 11px; line-height: 1.65; }
.citations { margin-top: 12px; }
.citations__label { display: block; margin-bottom: 5px; color: #72878d; font-size: 9px; font-weight: 600; letter-spacing: 0.5px; }
.citation { display: block; width: 100%; padding: 9px 10px; border: 1px solid #dce9e6; border-radius: 7px; background: white; text-align: left; cursor: pointer; transition: 0.16s ease; }
.citation + .citation { margin-top: 5px; }
.citation:hover { border-color: #9ec8c1; background: #f8fcfb; }
.citation__top { display: flex; align-items: center; justify-content: space-between; gap: 10px; color: var(--teal); font-size: 10px; }
.citation__top .time-text { font-weight: 600; }
.citation__top > span:last-child { color: #7f9699; font-size: 10px; }
.citation__text { display: block; margin-top: 4px; color: #4d676f; font-size: 12px; line-height: 1.7; overflow-wrap: anywhere; }
.answer-meta { display: flex; gap: 5px; margin: 10px 0 0; color: #9aa9ac; font-size: 10px; }
.answer-loading { display: flex; align-items: center; gap: 10px; padding: 13px; border: 1px dashed #d7e6e3; border-radius: 9px; background: #fafdfc; }
.answer-loading__icon { width: 30px; height: 30px; display: grid; place-items: center; border-radius: 8px; background: #eaf6f3; color: var(--teal); }
.answer-loading strong { display: block; color: #3a625f; font-size: 11px; }
.answer-loading span:not(.answer-loading__icon) { display: block; color: #8a9b9e; font-size: 9px; }
@media (max-width: 520px) {
  .question-panel { padding: 17px; }
  .mock-control small, .session-label, .shortcut { display: none; }
  .composer__footer .el-button { margin-left: auto; }
}
</style>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, shallowRef, watch } from "vue";
import { Close, Position } from "@element-plus/icons-vue";
import { askAssistant, assistantUsesApi, type AssistantMessage } from "@/api/assistant";
import { toApiError } from "@/api/http";
import { MAX_QUESTION_LENGTH } from "@/utils/format";
import { sessionState } from "@/stores/session";

interface Point { x: number; y: number }

const size = 56;
const margin = 12;
const gap = 10;
const launcher = ref<HTMLButtonElement>();
const panel = ref<HTMLElement>();
const conversation = ref<HTMLElement>();
const position = ref<Point>();
const viewport = ref(readViewport());
const overlayTarget = shallowRef<HTMLElement | string>("body");
const open = ref(false);
const dragging = ref(false);
const messages = ref<AssistantMessage[]>([]);
const draft = ref("");
const sending = ref(false);
const error = ref("");
const answerMode = ref<"generative" | "guide">();
const assistantStatus = computed(() => !sessionState.user.value || !assistantUsesApi ? "站内使用指南 · 内置问答" : answerMode.value === "guide" ? "站内指引 · 当前使用基础回答" : answerMode.value === "generative" ? "在线助教 · 模型回答" : "在线助教 · 站内使用问答");
const prompts = ["课迹能做什么？", "怎么上传课程？", "怎么用原文问答？"];

let drag: { pointerId: number; origin: Point; start: Point } | undefined;

function readViewport() {
  const visible = window.visualViewport;
  return {
    left: visible?.offsetLeft ?? 0,
    top: visible?.offsetTop ?? 0,
    width: visible?.width ?? window.innerWidth,
    height: visible?.height ?? window.innerHeight,
  };
}

function updateViewport() {
  viewport.value = readViewport();
}

function updateFullscreen() {
  const element = document.fullscreenElement;
  overlayTarget.value = element instanceof HTMLElement ? element : "body";
  updateViewport();
}

function clamp(value: number, min: number, max: number) {
  return Math.max(min, Math.min(value, max));
}

const launcherPosition = computed(() => {
  const frame = viewport.value;
  const left = frame.left + margin;
  const bottom = frame.top + frame.height - margin;
  const point = position.value ?? { x: left, y: bottom - size };
  return {
    x: clamp(point.x, left, frame.left + frame.width - margin - size),
    y: clamp(point.y, frame.top + margin, bottom - size),
  };
});

const panelStyle = computed(() => {
  const frame = viewport.value;
  const button = launcherPosition.value;
  const width = Math.min(350, frame.width - 2 * margin);
  const top = frame.top + margin;
  const bottom = frame.top + frame.height - margin;
  const above = button.y - gap - top;
  const below = bottom - button.y - size - gap;
  const maxHeight = Math.min(430, bottom - top);
  const placeAbove = above >= maxHeight || above >= below;
  const height = Math.min(maxHeight, Math.max(260, placeAbove ? above : below));
  const y = placeAbove ? button.y - gap - height : button.y + size + gap;
  return {
    left: `${clamp(button.x, frame.left + margin, frame.left + frame.width - margin - width)}px`,
    top: `${clamp(y, top, bottom - height)}px`,
    width: `${width}px`,
    height: `${height}px`,
  };
});

function startDrag(event: PointerEvent) {
  if (!event.isPrimary || event.button !== 0) return;
  drag = {
    pointerId: event.pointerId,
    origin: launcherPosition.value,
    start: { x: event.clientX, y: event.clientY },
  };
  launcher.value?.setPointerCapture(event.pointerId);
}

function moveDrag(event: PointerEvent) {
  if (drag?.pointerId !== event.pointerId) return;
  const x = event.clientX - drag.start.x;
  const y = event.clientY - drag.start.y;
  if (!dragging.value && Math.hypot(x, y) < 6) return;
  dragging.value = true;
  position.value = { x: drag.origin.x + x, y: drag.origin.y + y };
}

function finishDrag(event: PointerEvent) {
  if (drag?.pointerId !== event.pointerId) return;
  const moved = dragging.value;
  if (moved) position.value = launcherPosition.value;
  dragging.value = false;
  drag = undefined;
  if (event.type === "pointerup" && !moved) void togglePanel();
}

function activateFromKeyboard(event: MouseEvent) {
  if (event.detail === 0) void togglePanel();
}

async function togglePanel() {
  if (open.value) {
    closePanel();
    return;
  }
  open.value = true;
  await nextTick();
  panel.value?.focus({ preventScroll: true });
}

function closePanel() {
  open.value = false;
  launcher.value?.focus({ preventScroll: true });
}

async function send(value: string) {
  const question = value.trim();
  if (!question || sending.value || question.length > MAX_QUESTION_LENGTH) return;

  const message: AssistantMessage = { role: "user", content: question };
  messages.value.push(message);
  draft.value = "";
  error.value = "";
  sending.value = true;
  try {
    const answer = await askAssistant(messages.value.slice(-13));
    answerMode.value = answer.mode;
    messages.value.push({ role: "assistant", content: answer.answer });
  } catch (cause) {
    messages.value.pop();
    draft.value = question;
    error.value = toApiError(cause).message;
  } finally {
    sending.value = false;
  }
}

watch([open, () => messages.value.length, sending], () => {
  if (conversation.value) conversation.value.scrollTop = conversation.value.scrollHeight;
}, { flush: "post" });

onMounted(() => {
  updateFullscreen();
  document.addEventListener("fullscreenchange", updateFullscreen);
  window.addEventListener("resize", updateViewport);
  window.visualViewport?.addEventListener("resize", updateViewport);
  window.visualViewport?.addEventListener("scroll", updateViewport);
});

onBeforeUnmount(() => {
  document.removeEventListener("fullscreenchange", updateFullscreen);
  window.removeEventListener("resize", updateViewport);
  window.visualViewport?.removeEventListener("resize", updateViewport);
  window.visualViewport?.removeEventListener("scroll", updateViewport);
});
</script>

<template>
  <Teleport :to="overlayTarget">
    <section
      v-if="open"
      id="global-assistant"
      ref="panel"
      class="assistant-panel"
      :style="panelStyle"
      role="dialog"
      aria-labelledby="global-assistant-title"
      tabindex="-1"
      @keydown.esc.stop="closePanel"
    >
      <header class="assistant-panel__header">
        <span class="assistant-panel__icon"><img src="/assistant-mark.svg" width="25" height="25" alt="" /></span>
        <div>
          <h2 id="global-assistant-title">课迹助教</h2>
          <span>{{ assistantStatus }}</span>
        </div>
        <button type="button" class="assistant-panel__close" aria-label="关闭课迹助教" @click="closePanel">
          <Close aria-hidden="true" />
        </button>
      </header>

      <div ref="conversation" class="assistant-panel__conversation">
        <p class="assistant-bubble">
          你好，我是课迹助教。课迹能把中文录课整理成章节提要，帮你按原文提问并回到讲解时间点。想了解怎么用吗？
        </p>
        <div v-if="!messages.length" class="assistant-panel__prompts">
          <button v-for="prompt in prompts" :key="prompt" type="button" :disabled="sending" @click="send(prompt)">
            {{ prompt }}
          </button>
        </div>
        <div class="assistant-panel__messages" role="log" aria-label="课迹助教对话">
          <p v-for="(message, index) in messages" :key="index" class="assistant-bubble" :class="{ 'is-user': message.role === 'user' }">
            <span class="sr-only">{{ message.role === "user" ? "你说" : "助教回复" }}</span>{{ message.content }}
          </p>
          <p v-if="sending" class="assistant-bubble">正在回答…</p>
        </div>
      </div>

      <form class="assistant-panel__form" @submit.prevent="send(draft)">
        <p v-if="error" class="assistant-panel__error" role="alert">{{ error }}</p>
        <div class="assistant-panel__input-row">
          <input v-model="draft" :maxlength="MAX_QUESTION_LENGTH" :disabled="sending" aria-label="给课迹助教的问题" placeholder="问问课迹怎么用…" />
          <button type="submit" class="assistant-panel__send" aria-label="发送问题" :disabled="sending || !draft.trim()">
            <Position aria-hidden="true" />
          </button>
        </div>
      </form>
    </section>

    <button
      ref="launcher"
      type="button"
      class="assistant-launcher"
      :class="{ 'is-dragging': dragging }"
      :style="{ left: `${launcherPosition.x}px`, top: `${launcherPosition.y}px`, width: `${size}px`, height: `${size}px` }"
      aria-label="课迹助教"
      aria-haspopup="dialog"
      :aria-expanded="open"
      :aria-controls="open ? 'global-assistant' : undefined"
      title="课迹助教 · 点击打开，拖动移动"
      @pointerdown="startDrag"
      @pointermove="moveDrag"
      @pointerup="finishDrag"
      @pointercancel="finishDrag"
      @lostpointercapture="finishDrag"
      @click="activateFromKeyboard"
    >
      <img src="/assistant-mark.svg" width="36" height="36" alt="" draggable="false" />
    </button>
  </Teleport>
</template>

<style scoped>
.assistant-launcher, .assistant-panel { position: fixed; z-index: 110; }
.assistant-launcher {
  display: grid;
  place-items: center;
  padding: 0;
  border: 1px solid var(--teal-dark);
  border-radius: 50%;
  background: linear-gradient(145deg, #168d8e, var(--teal-dark) 80%);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.18), 0 5px 16px rgba(0, 86, 89, 0.25);
  cursor: grab;
  touch-action: none;
  user-select: none;
}
.assistant-launcher:hover { background: var(--teal-dark); }
.assistant-launcher.is-dragging { cursor: grabbing; }
.assistant-launcher img { display: block; pointer-events: none; }
.assistant-panel {
  z-index: 111;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  border: 1px solid var(--line);
  border-radius: 16px;
  background: #fff;
  box-shadow: 0 14px 40px rgba(25, 62, 70, 0.2);
  color: var(--ink);
  font-size: 13px;
  line-height: 1.65;
}
.assistant-panel:focus { outline: none; }
.assistant-panel__header {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 14px;
  border-bottom: 1px solid var(--line);
  background: var(--teal-soft);
}
.assistant-panel__icon { display: grid; place-items: center; width: 36px; height: 36px; flex-shrink: 0; border-radius: 10px; background: var(--teal-dark); }
.assistant-panel__header h2 { margin: 0; font-size: 15px; line-height: 1.4; }
.assistant-panel__header div > span { color: var(--muted); font-size: 11px; }
.assistant-panel__close {
  display: grid;
  place-items: center;
  width: 32px;
  height: 32px;
  margin-left: auto;
  padding: 0;
  border: 0;
  border-radius: 8px;
  background: transparent;
  color: var(--muted);
  cursor: pointer;
}
.assistant-panel__close:hover { background: #d8ebe8; color: var(--teal-dark); }
.assistant-panel__close svg { width: 16px; }
.assistant-panel__conversation { flex: 1; min-height: 0; padding: 14px; overflow-y: auto; overscroll-behavior: contain; }
.assistant-panel__messages { display: flex; flex-direction: column; gap: 9px; margin-top: 9px; }
.assistant-bubble { align-self: flex-start; max-width: 92%; margin: 0; padding: 9px 11px; border-radius: 10px; background: #f2f6f6; overflow-wrap: anywhere; white-space: pre-wrap; }
.assistant-bubble.is-user { align-self: flex-end; background: var(--teal-soft); color: var(--teal-dark); }
.assistant-panel__prompts { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 10px; }
.assistant-panel__prompts button { padding: 4px 8px; border: 1px solid var(--line); border-radius: 99px; background: #fff; color: var(--teal-dark); font-size: 11px; cursor: pointer; }
.assistant-panel__prompts button:hover { background: var(--teal-soft); }
.assistant-panel__form { padding: 10px 12px; border-top: 1px solid var(--line); }
.assistant-panel__error { margin: 0 0 7px; color: var(--danger); font-size: 12px; overflow-wrap: anywhere; }
.assistant-panel__input-row { display: flex; gap: 7px; }
.assistant-panel__input-row input { flex: 1; min-width: 0; padding: 7px 9px; border: 1px solid var(--line); border-radius: 8px; background: #fff; color: var(--ink); font-size: 16px; }
.assistant-panel__send { display: grid; place-items: center; width: 40px; padding: 0; border: 0; border-radius: 8px; background: var(--teal); color: #fff; cursor: pointer; }
.assistant-panel__send:disabled { background: #e1ecea; color: var(--muted); cursor: default; }
.assistant-panel__send svg { width: 17px; }
</style>

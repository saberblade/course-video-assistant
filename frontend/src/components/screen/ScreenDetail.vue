<script setup lang="ts">
import { computed, ref } from "vue";
import { STATUS_META, type KnowledgeNode } from "@/data/knowledgeMap";
import { formatTime } from "@/utils/format";

const props = defineProps<{ node: KnowledgeNode | null; open: boolean; sampleAvailable: boolean }>();
const emit = defineEmits<{ close: []; go: [node: KnowledgeNode] }>();

const copied = ref(false);
const meta = computed(() => (props.node ? STATUS_META[props.node.status] : null));

async function copyQuote() {
  if (!props.node) return;
  try {
    await navigator.clipboard.writeText(`${props.node.name}（${formatTime(props.node.time)}）：${props.node.quote}`);
    copied.value = true;
    window.setTimeout(() => (copied.value = false), 1600);
  } catch {
    copied.value = false;
  }
}
</script>

<template>
  <aside class="scr-detail" :class="{ 'is-open': props.open }" aria-label="知识点详情">
    <div class="scr-detail__head">
      <div>
        <div class="scr-detail__kicker">KNOWLEDGE POINT</div>
        <h2>{{ props.node?.name ?? "未选择知识点" }}</h2>
      </div>
      <button type="button" class="scr-detail__close" aria-label="关闭详情" @click="emit('close')">×</button>
    </div>

    <div v-if="props.node" class="scr-detail__body">
      <div class="scr-detail__row">
        <span>示例掌握状态</span>
        <b :style="{ color: meta?.color }">{{ meta?.label }}</b>
      </div>
      <div class="scr-detail__row">
        <span>原文出现次数</span>
        <b>{{ props.node.hits }} 次</b>
      </div>
      <div class="scr-detail__row">
        <span>所属章节</span>
        <b>{{ props.node.chapter }}</b>
      </div>
      <div class="scr-detail__row">
        <span>示例时间点</span>
        <b class="scr-detail__time">{{ formatTime(props.node.time) }}</b>
      </div>

      <blockquote class="scr-detail__quote">
        <em>示例摘录</em>
        {{ props.node.quote }}
      </blockquote>

      <div class="scr-detail__act">
        <button v-if="props.sampleAvailable" type="button" class="scr-btn scr-btn--primary" @click="emit('go', props.node)">
          演示定位到 {{ formatTime(props.node.time) }}
        </button>
        <button type="button" class="scr-btn" @click="copyQuote">
          {{ copied ? "已复制" : "复制示例" }}
        </button>
      </div>

      <p class="scr-detail__note">
        {{ props.sampleAvailable ? "此时间点用于演示课程的定位交互。" : "可在「我的课程」打开已处理视频，通过章节或问答引用定位原文。" }}
      </p>
    </div>

    <div v-else class="scr-detail__empty">
      <p>点击地图上的知识点</p>
      <p>查看示例摘录与时间点</p>
    </div>
  </aside>
</template>

<style scoped>
.scr-detail__note {
  margin: 14px 0 0;
  color: var(--scr-text-faint);
  font-size: 11px;
  line-height: 1.75;
}
</style>

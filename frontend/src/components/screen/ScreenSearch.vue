<script setup lang="ts">
import { computed, ref } from "vue";
import type { KnowledgeNode } from "@/data/knowledgeMap";
import { formatTime } from "@/utils/format";

const props = defineProps<{ nodes: KnowledgeNode[]; matched: number; keyword: string }>();
const emit = defineEmits<{ change: [value: string]; pick: [node: KnowledgeNode] }>();

const input = ref<HTMLInputElement>();
const focused = ref(false);
const draft = ref("");

const suggestions = computed(() => {
  const key = draft.value.trim();
  if (!key) return [];
  return props.nodes
    .filter((node) => node.name.includes(key) || node.chapter.includes(key))
    .slice(0, 5);
});

function onInput() {
  focused.value = true;
  emit("change", draft.value);
}

function onFocusOut(event: FocusEvent) {
  const next = event.relatedTarget;
  if (!(next instanceof Node && (event.currentTarget as HTMLElement).contains(next))) {
    focused.value = false;
  }
}

function clear() {
  draft.value = "";
  emit("change", "");
  input.value?.focus();
}

function pick(node: KnowledgeNode) {
  draft.value = node.name;
  emit("change", node.name);
  emit("pick", node);
  input.value?.focus();
  focused.value = false;
}
</script>

<template>
  <div class="scr-search" @focusin="focused = true" @focusout="onFocusOut" @keydown.esc="focused = false">
    <div class="scr-search__box">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <circle cx="11" cy="11" r="7" />
        <path d="m20 20-3.5-3.5" stroke-linecap="round" />
      </svg>
      <input
        ref="input"
        v-model="draft"
        type="search"
        placeholder="搜索知识点或章节…"
        aria-label="搜索知识点"
        @input="onInput"
      />
      <button v-if="draft" type="button" class="scr-search__clear" aria-label="清空搜索" @click="clear">×</button>
    </div>

    <p v-if="props.keyword" class="scr-search__hint">
      匹配 <b>{{ props.matched }}</b> / {{ props.nodes.length }} 个知识点
    </p>

    <div v-if="focused && suggestions.length" class="scr-suggest">
      <button v-for="node in suggestions" :key="node.id" type="button" @click="pick(node)">
        {{ node.name }}
        <span>{{ formatTime(node.time) }}</span>
      </button>
    </div>
  </div>
</template>

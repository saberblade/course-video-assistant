<script setup lang="ts">
import { STATUS_META, type KnowledgeStatus } from "@/data/knowledgeMap";

const props = defineProps<{
  counts: Record<KnowledgeStatus, number>;
  hidden: KnowledgeStatus[];
  stats: { label: string; value: string; unit?: string }[];
}>();

const emit = defineEmits<{ toggle: [status: KnowledgeStatus] }>();

const rows: KnowledgeStatus[] = ["ok", "warn", "bad"];
</script>

<template>
  <aside class="scr-legend">
    <div class="scr-legend__title">
      <span>状态图例</span>
      <span>点击筛选</span>
    </div>

    <button
      v-for="status in rows"
      :key="status"
      type="button"
      class="scr-legend__row"
      :class="{ 'is-off': props.hidden.includes(status) }"
      @click="emit('toggle', status)"
    >
      <span class="scr-dot" :class="`scr-dot--${status}`" />
      <span>{{ STATUS_META[status].label }}</span>
      <b :style="{ color: STATUS_META[status].color }">{{ props.counts[status] }}</b>
    </button>

    <div class="scr-legend__stats">
      <div v-for="item in props.stats" :key="item.label">
        <span>{{ item.label }}</span>
        <strong>{{ item.value }}<em v-if="item.unit">{{ item.unit }}</em></strong>
      </div>
    </div>
  </aside>
</template>

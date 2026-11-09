<script setup lang="ts">
import { computed, ref } from "vue";
import { ArrowRight, CollectionTag, Position } from "@element-plus/icons-vue";
import type { Chapter, TranscriptSegment } from "@/types";
import { formatTime } from "@/utils/format";

const props = defineProps<{
  chapters: Chapter[];
  segments: TranscriptSegment[];
  loading: boolean;
  error: string;
}>();

const emit = defineEmits<{ seek: [seconds: number] }>();
const expandedIds = ref<Set<string>>(new Set());
const segmentMap = computed(() => new Map(props.segments.map((segment) => [segment.id, segment])));

function toggleSources(id: string) {
  const next = new Set(expandedIds.value);
  if (next.has(id)) next.delete(id);
  else next.add(id);
  expandedIds.value = next;
}

function sourceSegments(chapter: Chapter): TranscriptSegment[] {
  return chapter.segment_ids
    .map((id) => segmentMap.value.get(id))
    .filter((segment): segment is TranscriptSegment => Boolean(segment));
}
</script>

<template>
  <div class="chapter-list">
    <div v-if="loading" class="chapter-skeleton">
      <el-skeleton v-for="index in 3" :key="index" :rows="2" animated />
    </div>
    <el-alert v-else-if="error" :title="error" type="warning" :closable="false" show-icon />
    <div v-else-if="!chapters.length" class="empty-inline">当前视频还没有可展示的章节提要。</div>
    <template v-else>
      <article v-for="chapter in chapters" :key="chapter.id" class="chapter">
        <button type="button" class="chapter__title" @click="emit('seek', chapter.start_sec)">
          <span class="chapter__time time-text"><el-icon><Position /></el-icon>{{ formatTime(chapter.start_sec) }}</span>
          <span class="chapter__name">{{ chapter.title.replace(/^\d{2}:\d{2}\s*/, "") || "章节提要" }}</span>
          <el-icon class="chapter__jump"><ArrowRight /></el-icon>
        </button>
        <p class="chapter__text">{{ chapter.text }}</p>
        <button
          v-if="chapter.segment_ids.length"
          type="button"
          class="source-toggle"
          :aria-expanded="expandedIds.has(chapter.id)"
          @click="toggleSources(chapter.id)"
        >
          <el-icon><CollectionTag /></el-icon>
          {{ expandedIds.has(chapter.id) ? "收起来源原文" : `查看 ${chapter.segment_ids.length} 条来源原文` }}
        </button>
        <div v-if="expandedIds.has(chapter.id)" class="sources">
          <button
            v-for="segment in sourceSegments(chapter)"
            :key="segment.id"
            type="button"
            class="source"
            @click="emit('seek', segment.start_sec)"
          >
            <span class="time-text">{{ formatTime(segment.start_sec) }}</span>
            <span>{{ segment.text }}</span>
          </button>
          <p v-if="!sourceSegments(chapter).length" class="source-empty">来源片段暂不可用</p>
        </div>
      </article>
    </template>
  </div>
</template>

<style scoped>
.chapter-list { margin-top: 4px; }
.chapter { padding: 15px 0; border-top: 1px solid #edf1f1; }
.chapter:first-child { border-top: 0; padding-top: 3px; }
.chapter__title { display: flex; align-items: center; gap: 8px; width: 100%; padding: 0; border: 0; background: transparent; color: var(--ink); text-align: left; cursor: pointer; }
.chapter__title:hover .chapter__name { color: var(--teal); }
.chapter__time { display: inline-flex; align-items: center; gap: 3px; padding: 3px 7px; border-radius: 5px; background: #eef7f5; color: var(--teal); font-size: 11px; flex-shrink: 0; }
.chapter__time svg { width: 11px; }
.chapter__name { font-size: 13px; font-weight: 650; }
.chapter__jump { margin-left: auto; color: #a1b3b5; font-size: 13px; }
.chapter__text { margin: 8px 0 9px 0; color: #506a72; font-size: 13px; line-height: 1.8; overflow-wrap: anywhere; }
.source-toggle { display: inline-flex; align-items: center; gap: 4px; padding: 0; border: 0; background: transparent; color: #7d9298; font-size: 12px; cursor: pointer; }
.source-toggle:hover { color: var(--teal); }
.source-toggle svg { width: 13px; }
.sources { margin: 10px 0 2px; padding: 4px 10px; border-left: 2px solid #dbe9e7; background: #fafcfb; }
.source { display: grid; grid-template-columns: 46px minmax(0, 1fr); gap: 8px; width: 100%; padding: 7px 0; border: 0; background: transparent; color: #526c73; text-align: left; font-size: 12px; line-height: 1.7; cursor: pointer; }
.source:hover { color: var(--teal); }
.source .time-text { color: #3d8279; }
.source-empty { margin: 6px 0; color: #8a9a9e; font-size: 11px; }
.chapter-skeleton { padding: 12px 0; }
.chapter-skeleton > div + div { margin-top: 8px; }
</style>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { ArrowRight, Check, CollectionTag, Search } from "@element-plus/icons-vue";
import { usePanZoom } from "@/composables/usePanZoom";
import type { Chapter } from "@/types";
import { formatTime } from "@/utils/format";

const props = defineProps<{
  chapters: Chapter[];
  reviewedIds: string[];
  savedIds: string[];
  activeId: string;
}>();
const emit = defineEmits<{ open: [chapter: Chapter] }>();
const keyword = ref("");
const filter = ref<"all" | "unmarked" | "saved">("all");
const viewport = ref<HTMLElement>();
const canvas = ref<HTMLElement>();
const pan = usePanZoom(viewport, canvas);
const { scale, transform, dragging } = pan;
const worldWidth = ref(1144);
const columns = ref(4);
const width = ref(0);
const height = ref(0);
const paths = ref<string[]>([]);
const announcements = ref("");
let observer: ResizeObserver | undefined;
let frame = 0;
let resetView = true;

const indexed = computed(() => props.chapters.map((chapter, index) => ({ chapter, number: index + 1 })));
const matched = computed(() => indexed.value.filter(({ chapter }) => {
  const statusMatch = filter.value === "all" || (filter.value === "saved" ? props.savedIds.includes(chapter.id) : !props.reviewedIds.includes(chapter.id));
  return statusMatch && `${chapter.title} ${chapter.text}`.toLowerCase().includes(keyword.value.trim().toLowerCase());
}));
const rows = computed(() => {
  const result = [];
  for (let i = 0; i < matched.value.length; i += columns.value) result.push(matched.value.slice(i, i + columns.value));
  return result;
});
const nextChapter = computed(() => indexed.value.find(({ chapter }) => !props.reviewedIds.includes(chapter.id)));
const filters = computed(() => [
  { key: "all" as const, label: "全部章节", count: props.chapters.length },
  { key: "unmarked" as const, label: "未标记", count: props.chapters.length - props.reviewedIds.length },
  { key: "saved" as const, label: "待回看", count: props.savedIds.length },
]);

function preview(text: string) {
  const copy = text.replace(/\s+/g, " ").trim();
  return copy.length > 44 ? `${copy.slice(0, 44)}…` : copy;
}
function choose(chapter: Chapter) {
  emit("open", chapter);
}
function resume() {
  if (!nextChapter.value) return;
  const node = [...(canvas.value?.querySelectorAll<HTMLElement>(".cr-stop") ?? [])].find(el => el.dataset.chapterId === nextChapter.value?.chapter.id);
  if (node) pan.reveal(node);
  emit("open", nextChapter.value.chapter);
}
function onStopFocus(event: FocusEvent) {
  const element = event.target;
  if (element instanceof HTMLElement && element.matches(":focus-visible")) void nextTick(() => pan.reveal(element));
}
function measure() {
  const element = canvas.value;
  const view = viewport.value;
  if (!element || !view) return;
  const nextColumns = Math.min(4, Math.max(1, matched.value.length));
  const nextWidth = Math.max(view.clientWidth, nextColumns * 270 + 64);
  if (nextColumns !== columns.value || nextWidth !== worldWidth.value) {
    columns.value = nextColumns;
    worldWidth.value = nextWidth;
    void nextTick(scheduleMeasure);
    return;
  }
  width.value = element.offsetWidth;
  height.value = element.offsetHeight;
  const origin = element.getBoundingClientRect();
  const nodes = [...element.querySelectorAll<HTMLElement>(".cr-node")].map(node => {
    const rect = node.getBoundingClientRect();
    return { x: (rect.left - origin.left + rect.width / 2) / scale.value, y: (rect.top - origin.top + rect.height / 2) / scale.value };
  });
  paths.value = nodes.slice(1).map((point, index) => {
    const previous = nodes[index]!;
    if (Math.abs(previous.y - point.y) < 2) return `M${previous.x} ${previous.y}H${point.x}`;
    if (columns.value === 1) return `M${previous.x} ${previous.y}H14V${point.y}H${point.x}`;
    const rightSide = Math.floor(index / columns.value) % 2 === 0;
    const edge = rightSide ? width.value - 14 : 14;
    const bend = rightSide ? -10 : 10;
    return `M${previous.x} ${previous.y}H${edge + bend}Q${edge} ${previous.y} ${edge} ${previous.y + 10}V${point.y - 10}Q${edge} ${point.y} ${edge + bend} ${point.y}H${point.x}`;
  });
  pan.layoutChanged(resetView);
  resetView = false;
}
function scheduleMeasure() {
  cancelAnimationFrame(frame);
  frame = requestAnimationFrame(measure);
}
watch([keyword, filter], () => { resetView = true; });
watch(() => props.chapters, () => { keyword.value = ""; filter.value = "all"; resetView = true; });
watch([rows, () => props.reviewedIds, () => props.savedIds], () => void nextTick(scheduleMeasure), { flush: "post" });
watch(matched, items => { announcements.value = `找到 ${items.length} 个章节`; });
onMounted(() => {
  observer = new ResizeObserver(scheduleMeasure);
  if (canvas.value) observer.observe(canvas.value);
  if (viewport.value) observer.observe(viewport.value);
  scheduleMeasure();
});
onBeforeUnmount(() => { observer?.disconnect(); cancelAnimationFrame(frame); });
</script>

<template>
  <section class="cr" aria-label="课程章节路线图">
    <header class="cr-heading">
      <div class="cr-heading-title"><span class="cr-symbol" aria-hidden="true"><i /><i /><i /></span><div><h2>章节画布</h2><p>滚轮上下移动 · 拖动查看 · 点击章节展开原文</p></div></div>
      <button v-if="nextChapter" type="button" class="cr-resume" @click="resume">{{ reviewedIds.length ? '继续复习' : '从这里开始' }}<span>第 {{ String(nextChapter.number).padStart(2, '0') }} 节</span><ArrowRight /></button>
      <span v-else class="cr-all-marked"><Check />全部章节已手动标记复习</span>
    </header>
    <div class="cr-toolbar">
      <div class="cr-filters" aria-label="筛选章节"><button v-for="item in filters" :key="item.key" type="button" :aria-pressed="filter === item.key" :class="{ 'is-active': filter === item.key }" @click="filter = item.key">{{ item.label }}<span>{{ item.count }}</span></button></div>
      <el-input v-model="keyword" placeholder="搜索章节里的内容" aria-label="搜索章节" clearable><template #prefix><Search /></template></el-input>
    </div>
    <div ref="viewport" class="cr-viewport" :class="{ 'is-dragging': dragging }" role="region" aria-label="章节画布，滚轮上下移动，拖动平移；方向键移动，加减号缩放，0复位" tabindex="0" @wheel="pan.onWheel" @pointerdown="pan.onPointerDown" @pointermove="pan.onPointerMove" @pointerup="pan.endPointer" @pointercancel="pan.endPointer" @lostpointercapture="pan.endPointer" @click.capture="pan.captureClick" @keydown="pan.onKeydown" @dragstart.prevent>
    <div ref="canvas" class="cr-canvas" :style="{ '--route-columns': columns, width: `${worldWidth}px`, transform }" :data-scale="scale.toFixed(3)">
      <svg v-if="paths.length" class="cr-track" :viewBox="`0 0 ${width} ${height}`" aria-hidden="true"><path v-for="(path, index) in paths" :key="index" :d="path" /></svg>
      <div v-for="(row, rowIndex) in rows" :key="rowIndex" class="cr-row" :class="{ 'cr-row--reverse': rowIndex % 2 === 1 && columns > 1 }">
        <button v-for="{ chapter, number } in row" :key="chapter.id" type="button" class="cr-stop" :data-chapter-id="chapter.id" :class="{ 'is-reviewed': reviewedIds.includes(chapter.id), 'is-selected': activeId === chapter.id }" :aria-label="`打开第 ${String(number).padStart(2, '0')} 节，${formatTime(chapter.start_sec)}`" :aria-pressed="activeId === chapter.id" @click="choose(chapter)" @focus="onStopFocus">
          <span class="cr-station"><span class="cr-node"><Check v-if="reviewedIds.includes(chapter.id)" /><span v-else>{{ String(number).padStart(2, '0') }}</span></span><time>{{ formatTime(chapter.start_sec) }}</time></span>
          <span class="cr-card"><span class="cr-card-top"><strong>第 {{ String(number).padStart(2, '0') }} 节</strong><span class="cr-range" aria-label="视频起止时间">{{ formatTime(chapter.start_sec) }}–{{ formatTime(chapter.end_sec) }}</span></span><span class="cr-preview">{{ preview(chapter.text) }}</span><span class="cr-card-bottom"><span v-if="savedIds.includes(chapter.id)" class="cr-saved"><CollectionTag />待回看</span><span v-else-if="reviewedIds.includes(chapter.id)" class="cr-reviewed-label">已复习</span><span v-else>原句预览</span><ArrowRight /></span></span>
        </button>
      </div>
    </div>
    <div v-if="!matched.length" class="cr-empty"><Search /><h3>没有匹配的章节</h3><p>{{ keyword ? '换个关键词，或清空搜索查看完整路线。' : '这个筛选下暂时没有章节，可以查看全部章节。' }}</p><button type="button" @click="keyword = ''; filter = 'all'">查看全部章节</button></div>
    </div>
    <footer class="cr-footer"><span><i />共 {{ chapters.length }} 节<span class="cr-footer-separator">·</span>已标记 {{ reviewedIds.length }} 节</span><div class="cr-view-controls" aria-label="画布视图"><button type="button" aria-label="缩小画布" :disabled="scale <= .2" @click="pan.zoomTo(scale / 1.2)">−</button><span class="cr-scale">{{ Math.round(scale * 100) }}%</span><button type="button" aria-label="放大画布" :disabled="scale >= 1.8" @click="pan.zoomTo(scale * 1.2)">+</button><button type="button" @click="pan.fit">全览</button><button type="button" @click="pan.reset">复位</button></div></footer>
    <span class="cr-sr" role="status" aria-live="polite">{{ announcements }}</span>
  </section>
</template>

<style scoped>
.cr { display: flex; flex-direction: column; flex: 1; min-height: 0; border: 1px solid #dbe6e3; border-radius: 16px; background: #fff; overflow: hidden; box-shadow: 0 8px 30px #254f4210; }
.cr-heading { display: flex; flex-shrink: 0; align-items: center; justify-content: space-between; gap: 24px; padding: 15px 24px; }
.cr-heading-title { display: flex; align-items: center; gap: 15px; }
.cr-heading h2 { margin: 0 0 4px; color: #234b4b; font-size: 16px; letter-spacing: -.4px; }
.cr-heading p { margin: 0; color: #8a9e98; font-size: 12px; }
.cr-symbol { display: flex; flex-direction: column; gap: 5px; position: relative; padding: 5px; }
.cr-symbol::before { content: ''; position: absolute; width: 1px; top: 6px; bottom: 6px; left: 9px; background: #8ebdb1; }
.cr-symbol i { z-index: 1; width: 9px; height: 9px; border: 2px solid #0f7d80; border-radius: 50%; background: #fff; }
.cr-symbol i:nth-child(2) { background: #0f7d80; }
.cr-resume { display: inline-flex; align-items: center; gap: 10px; padding: 10px 15px; border: none; border-radius: 8px; background: #0f7d80; color: #fff; font: inherit; font-size: 12px; cursor: pointer; }
.cr-resume:hover { background: #096b6e; }.cr-resume span { color: #bce1db; font-size: 11px; }.cr-resume svg { width: 14px; }
.cr-all-marked { display: flex; align-items: center; gap: 5px; color: #47816e; font-size: 12px; }.cr-all-marked svg { width: 16px; }
.cr-toolbar { display: flex; flex-shrink: 0; align-items: center; justify-content: space-between; gap: 20px; padding: 11px 24px; border-top: 1px solid #edf2ef; border-bottom: 1px solid #edf2ef; }
.cr-toolbar > .el-input { max-width: 265px; }.cr-toolbar :deep(.el-input__wrapper) { background: #f8faf9; border-radius: 7px; box-shadow: none; }.cr-toolbar :deep(.el-input__wrapper.is-focus) { box-shadow: 0 0 0 1px #91bdb2; }.cr-toolbar :deep(.el-input svg) { width: 14px; }
.cr-filters { display: flex; gap: 7px; }.cr-filters button { display: flex; align-items: center; gap: 8px; padding: 6px 10px; border: 1px solid transparent; border-radius: 6px; background: transparent; font: inherit; font-size: 12px; color: #80968d; cursor: pointer; white-space: nowrap; }.cr-filters button span { font-family: Consolas, monospace; font-size: 10px; color: #96a99f; }.cr-filters button.is-active { border-color: #d7e8df; background: #f0f7f2; color: #366f57; }.cr-filters button.is-active span { color: #4d8c6f; }
.cr-viewport { position: relative; flex: 1; min-height: 300px; overflow: clip; touch-action: none; user-select: none; cursor: grab; background: radial-gradient(circle,#d1e0d7 1px,transparent 1px) 0 0 / 20px 20px,#fafcf9; }
.cr-viewport.is-dragging,.cr-viewport.is-dragging * { cursor: grabbing !important; }
.cr-viewport:focus-visible { outline: 2px solid #5d9f8d; outline-offset: -3px; }
.cr-canvas { position: absolute; top: 0; left: 0; padding: 32px; transform-origin: 0 0; will-change: transform; }
.cr-track { position: absolute; inset: 0; width: 100%; height: 100%; pointer-events: none; z-index: 0; overflow: visible; }.cr-track path { fill: none; stroke: #b1cfc1; stroke-width: 1.5; stroke-dasharray: 5 5; }
.cr-row { display: grid; grid-template-columns: repeat(var(--route-columns), minmax(0,1fr)); gap: 24px; position: relative; z-index: 1; }.cr-row + .cr-row { margin-top: 28px; }.cr-row--reverse { direction: rtl; }
.cr-stop { display: block; direction: ltr; width: 100%; min-width: 0; padding: 0; border: none; background: transparent; text-align: left; color: inherit; font: inherit; cursor: pointer; border-radius: 11px; }
.cr-station { display: flex; align-items: center; gap: 9px; height: 36px; margin-bottom: 12px; }.cr-node { display: grid; place-items: center; width: 34px; height: 34px; flex-shrink: 0; border: 1.5px solid #aac9bd; border-radius: 50%; background: #fafcf9; color: #6f9685; font: 12px Consolas, monospace; transition: .16s; }.cr-node svg { width: 15px; }
.cr-station time { padding: 3px 7px; background: #fafcf9; font: 11px Consolas, monospace; color: #809c8b; }
.cr-card { display: flex; flex-direction: column; padding: 19px 19px 15px; border: 1px solid #dce7df; border-radius: 11px; background: #fff; box-shadow: 0 3px 10px #304e3c04; transition: border-color .16s,box-shadow .16s,transform .16s; }
.cr-card-top { display: flex; align-items: center; justify-content: space-between; gap: 10px; }.cr-card-top strong { font-size: 16px; font-weight: 650; color: #2d5142; }.cr-card-top > span { font: 10px Consolas, monospace; color: #738e7e; white-space: nowrap; }
.cr-preview { display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; min-height: 48px; margin: 12px 0 17px; color: #647d6c; font-size: 13px; line-height: 1.85; overflow-wrap: anywhere; }
.cr-card-bottom { display: flex; align-items: center; justify-content: space-between; gap: 12px; color: #a2b2a6; font-size: 10px; }.cr-card-bottom > svg { width: 14px; color: #8aab98; }.cr-saved { display: inline-flex; align-items: center; gap: 4px; color: #b08a48; }.cr-saved svg { width: 11px; }.cr-reviewed-label { color: #659b7d; }
.cr-stop:hover .cr-card { border-color: #87b69d; box-shadow: 0 5px 18px #2d715216; transform: translateY(-2px); }.cr-stop:hover .cr-node { border-color: #3a9276; color: #287355; }.cr-stop.is-selected .cr-card { border-color: #0f7d80; background: #f4fbf8; }.cr-stop.is-selected .cr-node { background: #0f7d80; border-color: #0f7d80; color: #fff; }.cr-stop.is-reviewed .cr-node { border-color: #80b49a; color: #579574; background: #edf6ef; }.cr-stop:focus-visible { outline: 3px solid #8abeb5; outline-offset: 5px; }
.cr-footer { display: flex; flex-shrink: 0; align-items: center; justify-content: space-between; gap: 18px; padding: 11px 24px; border-top: 1px solid #e7eee8; font-size: 10px; color: #91a295; }.cr-footer > span:first-child { display: flex; align-items: center; flex-wrap: wrap; gap: 7px; }.cr-footer i { width: 5px; height: 5px; border-radius: 50%; background: #93b9a3; }.cr-footer-separator { color: #c5d4c8; }.cr-footer button { display: inline-flex; align-items: center; justify-content: center; min-width: 27px; min-height: 27px; padding: 3px 7px; border: 1px solid #dce8e0; border-radius: 5px; background: #fff; color: #4a8163; font: inherit; font-size: 12px; white-space: nowrap; cursor: pointer; }.cr-footer button:hover { background: #edf5f0; }.cr-footer button:disabled { opacity: .35; cursor: default; }.cr-view-controls { display: flex; align-items: center; gap: 6px; }.cr-scale { min-width: 36px; text-align: center; color: #60816e; font: 11px Consolas,monospace; }
.cr-empty { position: absolute; inset: 0; z-index: 1; display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 30px 20px; text-align: center; background: #fafcf9; }.cr-empty > svg { width: 30px; color: #8db9a1; }.cr-empty h3 { margin: 12px 0 8px; font-size: 17px; color: #537361; }.cr-empty p { margin: 0 0 18px; color: #92a698; font-size: 12px; }.cr-empty button { border: 1px solid #bbd3c4; border-radius: 6px; background: #fff; color: #4b8061; padding: 7px 14px; cursor: pointer; }
.cr-sr { position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0,0,0,0); white-space: nowrap; border: 0; }
@media (max-width:700px) { .cr-heading { padding: 13px 16px; gap: 12px; }.cr-heading-title { gap: 10px; }.cr-heading h2 { font-size: 15px; }.cr-heading p { font-size: 10px; }.cr-symbol { display: none; }.cr-resume { padding: 7px 10px; gap: 5px; font-size: 11px; }.cr-resume span { display: none; }.cr-toolbar { padding: 10px 16px; flex-direction: column; align-items: stretch; gap: 9px; }.cr-toolbar > .el-input { max-width: none; }.cr-filters { gap: 3px; }.cr-filters button { padding-inline: 8px; gap: 6px; font-size: 11px; }.cr-footer { padding: 10px 12px; gap: 10px; }.cr-footer > span:first-child { gap: 4px; font-size: 9px; }.cr-view-controls { gap: 4px; }.cr-footer button { padding-inline: 5px; min-width: 24px; }.cr-viewport { min-height: 280px; } }
@media (prefers-reduced-motion:reduce) { .cr-card,.cr-node { transition: none; }.cr-stop:hover .cr-card { transform: none; } }
</style>

<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from "vue";
import {
  STATUS_META,
  knowledgeOutline,
  linkPath,
  type KnowledgeLink,
  type KnowledgeModule,
  type KnowledgeNode,
  type KnowledgeStatus,
} from "@/data/knowledgeMap";

const props = defineProps<{
  nodes: KnowledgeNode[];
  modules: KnowledgeModule[];
  links: KnowledgeLink[];
  activeId: string;
  keyword: string;
  hidden: KnowledgeStatus[];
}>();

const emit = defineEmits<{ select: [node: KnowledgeNode]; scale: [value: number] }>();

const scale = ref(1);
const pan = ref({ x: 0, y: 0 });
const tip = ref<{ node: KnowledgeNode; x: number; y: number } | null>(null);
const canvas = ref<HTMLElement>();

const nodeMap = computed(() => new Map(props.nodes.map((node) => [node.id, node])));

const dimmed = computed(() => {
  const key = props.keyword.trim();
  if (!key) return new Set<string>();
  return new Set(
    props.nodes.filter((node) => !node.name.includes(key) && !node.chapter.includes(key)).map((node) => node.id),
  );
});

const viewTransform = computed(
  () => `translate(${600 + pan.value.x} ${380 + pan.value.y}) scale(${scale.value}) translate(-600 -380)`,
);

function colorOf(status: KnowledgeStatus) {
  return STATUS_META[status].color;
}

function isDim(node: KnowledgeNode) {
  return props.hidden.includes(node.status) || dimmed.value.has(node.id);
}

function onEnter(node: KnowledgeNode, event: MouseEvent) {
  const rect = canvas.value?.getBoundingClientRect();
  if (!rect) return;
  tip.value = { node, x: event.clientX - rect.left, y: event.clientY - rect.top - 38 };
}

function onMove(event: MouseEvent) {
  if (!tip.value) return;
  const rect = canvas.value?.getBoundingClientRect();
  if (!rect) return;
  tip.value = { ...tip.value, x: event.clientX - rect.left, y: event.clientY - rect.top - 38 };
}

function onLeave() {
  tip.value = null;
}

/* --- 拖拽平移 --- */
let drag: { x: number; y: number; px: number; py: number; moved: boolean } | null = null;

function onDown(event: MouseEvent) {
  if (event.button !== 0) return;
  drag = { x: event.clientX, y: event.clientY, px: pan.value.x, py: pan.value.y, moved: false };
}

function onDrag(event: MouseEvent) {
  if (!drag) return;
  const dx = event.clientX - drag.x;
  const dy = event.clientY - drag.y;
  if (Math.abs(dx) > 3 || Math.abs(dy) > 3) drag.moved = true;
  if (drag.moved) pan.value = { x: drag.px + dx, y: drag.py + dy };
}

function onUp() {
  drag = null;
}

function onWheel(event: WheelEvent) {
  const next = scale.value + (event.deltaY > 0 ? -0.08 : 0.08);
  applyScale(next);
}

function applyScale(value: number) {
  scale.value = Math.min(1.8, Math.max(0.7, Number(value.toFixed(2))));
  if (scale.value === 1) pan.value = { x: 0, y: 0 };
  emit("scale", scale.value);
}

function zoomIn() {
  applyScale(scale.value + 0.12);
}

function zoomOut() {
  applyScale(scale.value - 0.12);
}

function reset() {
  pan.value = { x: 0, y: 0 };
  applyScale(1);
}

onBeforeUnmount(() => {
  drag = null;
});

defineExpose({ zoomIn, zoomOut, reset });
</script>

<template>
  <div ref="canvas" class="scr-map" @mousemove="onMove">
    <svg
      class="scr-map__svg"
      viewBox="110 90 980 580"
      preserveAspectRatio="xMidYMid meet"
      role="img"
      aria-label="课程知识点关系图"
      @mousedown="onDown"
      @mousemove="onDrag"
      @mouseup="onUp"
      @mouseleave="onUp"
      @wheel.prevent="onWheel"
    >
      <defs>
        <filter id="scrNodeGlow" x="-140%" y="-140%" width="380%" height="380%">
          <feDropShadow dx="0" dy="1.2" stdDeviation="1.4" flood-color="#1d2a2e" flood-opacity="0.22" />
        </filter>
        <filter id="scrRegionGlow" x="-25%" y="-25%" width="150%" height="150%">
          <feDropShadow dx="0" dy="3" stdDeviation="4" flood-color="#0f7d80" flood-opacity="0.16" />
        </filter>
        <filter id="scrLineGlow" x="-60%" y="-60%" width="220%" height="220%">
          <feDropShadow dx="0" dy="0" stdDeviation="1.2" flood-color="#0f7d80" flood-opacity="0.35" />
        </filter>
        <radialGradient id="scrCoreFill" cx="36%" cy="30%" r="72%">
          <stop offset="0%" stop-color="#ffffff" stop-opacity="0.9" />
          <stop offset="58%" stop-color="#ffffff" stop-opacity="0.22" />
          <stop offset="100%" stop-color="#ffffff" stop-opacity="0" />
        </radialGradient>
        <pattern id="scrDotPattern" width="9" height="9" patternUnits="userSpaceOnUse">
          <circle cx="1.6" cy="1.6" r="0.72" fill="#0f7d80" fill-opacity="0.26" />
        </pattern>
      </defs>

      <g :transform="viewTransform">
        <!-- 区块 -->
        <g>
          <path class="scr-region-outline" :d="knowledgeOutline" />
          <path
            v-for="mod in props.modules"
            :key="mod.id"
            class="scr-region"
            :class="{ 'scr-region--deep': mod.deep }"
            :data-module="mod.id"
            :d="mod.path"
          />
          <path class="scr-region-texture" :d="knowledgeOutline" />
          <text
            v-for="mod in props.modules"
            :key="`${mod.id}-label`"
            class="scr-region__label"
            :x="mod.labelX"
            :y="mod.labelY"
          >
            {{ mod.name }}
          </text>
        </g>

        <!-- 连线 -->
        <g>
          <path
            v-for="link in props.links"
            :key="`${link.from}-${link.to}`"
            class="scr-link"
            :class="{ 'is-active': props.activeId === link.from || props.activeId === link.to }"
            :d="linkPath(nodeMap.get(link.from)!, nodeMap.get(link.to)!)"
          />
        </g>

        <!-- 节点 -->
        <g>
          <g
            v-for="node in props.nodes"
            :key="node.id"
            class="scr-node"
            :class="{
              'is-active': props.activeId === node.id,
              'is-dim': isDim(node),
              'is-hit': !!props.keyword && !dimmed.has(node.id),
            }"
            :transform="`translate(${node.x} ${node.y})`"
            role="button"
            tabindex="0"
            :aria-label="`${node.name}，${STATUS_META[node.status].label}`"
            @click.stop="emit('select', node)"
            @keydown.enter.stop="emit('select', node)"
            @mouseenter="onEnter(node, $event)"
            @mouseleave="onLeave"
          >
            <circle class="scr-node__pulse" r="11" :stroke="colorOf(node.status)" />
            <circle class="scr-node__halo" r="15" :stroke="colorOf(node.status)" />
            <circle class="scr-node__ring" r="7.6" :stroke="colorOf(node.status)" />
            <circle
              class="scr-node__core"
              r="5.8"
              :fill="colorOf(node.status)"
              filter="url(#scrNodeGlow)"
            />
            <circle r="2.2" fill="url(#scrCoreFill)" />
            <text class="scr-node__label" y="-25">{{ node.name }}</text>
            <text class="scr-node__value" y="30">{{ node.hits }} 次</text>
          </g>
        </g>
      </g>
    </svg>

    <div v-if="tip" class="scr-tip" :style="{ left: `${tip.x}px`, top: `${tip.y}px` }">
      <div class="scr-tip__name">
        <span class="scr-dot" :class="`scr-dot--${tip.node.status}`" />
        {{ tip.node.name }}
      </div>
      <div class="scr-tip__meta">
        {{ STATUS_META[tip.node.status].label }} · 出现 {{ tip.node.hits }} 次 · {{ tip.node.chapter }}
      </div>
      <p class="scr-tip__text">{{ tip.node.quote }}</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from "vue";
import {
  STATUS_META,
  knowledgeModules,
  knowledgeNodes,
  statusCounts,
  type KnowledgeNode,
} from "@/data/knowledgeMap";
import { formatTime } from "@/utils/format";

const props = defineProps<{ weakOnly?: boolean }>();
const emit = defineEmits<{ goto: [node: KnowledgeNode]; openMap: []; openWeak: [] }>();

const total = knowledgeNodes.length;
const counts = statusCounts;
const rate = Math.round(((counts.ok + counts.warn * 0.5) / total) * 100);

const rows = (["ok", "warn", "bad"] as const).map((status) => ({
  status,
  label: STATUS_META[status].label,
  color: STATUS_META[status].color,
  value: counts[status],
  percent: Math.round((counts[status] / total) * 100),
}));

const moduleStats = computed(() =>
  knowledgeModules.map((module) => {
    const nodes = knowledgeNodes.filter((node) => node.module === module.id);
    const score = nodes.reduce((sum, node) => sum + (node.status === "ok" ? 1 : node.status === "warn" ? 0.5 : 0), 0);
    const percent = Math.round((score / nodes.length) * 100);
    return {
      id: module.id,
      name: module.name,
      total: nodes.length,
      ok: nodes.filter((node) => node.status === "ok").length,
      warn: nodes.filter((node) => node.status === "warn").length,
      bad: nodes.filter((node) => node.status === "bad").length,
      percent,
      color: percent >= 70 ? "#159263" : percent >= 45 ? "#ad7008" : "#b53f34",
    };
  }),
);

const weakNodes = computed(() =>
  [...knowledgeNodes]
    .filter((node) => node.status !== "ok")
    .sort((a, b) => (a.status === b.status ? a.time - b.time : a.status === "bad" ? -1 : 1)),
);

const planNodes = computed(() => weakNodes.value.slice(0, 3));

const chapterStats = computed(() => {
  const map = new Map<string, { total: number; score: number }>();
  for (const node of knowledgeNodes) {
    const entry = map.get(node.chapter) ?? { total: 0, score: 0 };
    entry.total += 1;
    entry.score += node.status === "ok" ? 1 : node.status === "warn" ? 0.5 : 0;
    map.set(node.chapter, entry);
  }
  return [...map.entries()].map(([chapter, entry]) => ({
    chapter,
    total: entry.total,
    percent: Math.round((entry.score / entry.total) * 100),
  }));
});

const moduleCount = new Set(knowledgeNodes.map((node) => node.module)).size;
</script>

<template>
  <section class="ana">
    <header class="ana-head">
      <div class="ana-head__title">
        <span class="section-kicker">{{ props.weakOnly ? "REVIEW PRIORITIES" : "LEARNING ANALYSIS" }} · 演示数据</span>
        <h1>{{ props.weakOnly ? "薄弱预警示例" : "学习分析示例" }}</h1>
        <p v-if="props.weakOnly">优先查看薄弱知识点，再按时间回看待复习内容。点选条目可查看原文与时间点。</p>
        <p v-else>查看「分类模型评估」示例的整体掌握分布、各模块表现与章节覆盖。</p>
      </div>
      <div v-if="props.weakOnly" class="ana-priorities">
        <div><span>优先复习</span><strong>{{ counts.bad }}</strong></div>
        <div><span>建议回看</span><strong>{{ counts.warn }}</strong></div>
      </div>
      <div v-else class="ana-score">
        <span>示例综合掌握度</span>
        <strong>{{ rate }}<em>%</em></strong>
        <i><b :style="{ width: `${rate}%` }" /></i>
        <small>已掌握计 1 · 待复习计 0.5 · 薄弱计 0</small>
      </div>
    </header>

    <div v-if="!props.weakOnly" class="ana-kpis">
      <div><span>知识点</span><strong>{{ total }}</strong><small>{{ moduleCount }} 个模块</small></div>
      <div><span>已掌握</span><strong class="is-ok">{{ counts.ok }}</strong><small>占 {{ rows[0].percent }}%</small></div>
      <div><span>待复习</span><strong class="is-warn">{{ counts.warn }}</strong><small>占 {{ rows[1].percent }}%</small></div>
      <div><span>薄弱点</span><strong class="is-bad">{{ counts.bad }}</strong><button type="button" class="ana-kpis__link" @click="emit('openWeak')">查看薄弱预警 →</button></div>
    </div>

    <div v-if="!props.weakOnly" class="ana-grid">
      <section class="ana-card" aria-labelledby="ana-dist">
        <header class="ana-card__head">
          <h2 id="ana-dist">掌握分布</h2>
          <span>共 {{ total }} 个知识点</span>
        </header>
        <div class="ana-dist">
          <div v-for="row in rows" :key="row.status" class="ana-dist__row">
            <span class="ana-dist__label">
              <i :style="{ background: row.color }" />
              {{ row.label }}
            </span>
            <div class="ana-dist__track">
              <b :style="{ width: `${row.percent}%`, background: row.color }" />
            </div>
            <span class="ana-dist__val">{{ row.value }}<em>{{ row.percent }}%</em></span>
          </div>
        </div>
        <div class="ana-stack">
          <i v-for="row in rows" :key="row.status" :style="{ width: `${row.percent}%`, background: row.color }" />
        </div>
        <p class="ana-tip">
          绿色节点可以直接跳过，琥珀色建议按时间点回看，红色需要重新听一遍原文。
        </p>
      </section>

      <section class="ana-card" aria-labelledby="ana-module">
        <header class="ana-card__head">
          <h2 id="ana-module">模块掌握度</h2>
          <span>按知识分区折算</span>
        </header>
        <div class="ana-rings">
          <div v-for="item in moduleStats" :key="item.id" class="ana-ring">
            <svg viewBox="0 0 84 84" role="img" :aria-label="`${item.name} 掌握度 ${item.percent}%`">
              <circle cx="42" cy="42" r="33" fill="none" stroke="#e8f0ef" stroke-width="6" />
              <circle
                cx="42"
                cy="42"
                r="33"
                fill="none"
                :stroke="item.color"
                stroke-width="6"
                stroke-linecap="round"
                :stroke-dasharray="`${(item.percent / 100) * 207.3} 999`"
                transform="rotate(-90 42 42)"
              />
              <text x="42" y="47" text-anchor="middle">{{ item.percent }}</text>
            </svg>
            <strong>{{ item.name }}</strong>
            <span>
              <i :style="{ background: STATUS_META.ok.color }" />{{ item.ok }}
              <i :style="{ background: STATUS_META.warn.color }" />{{ item.warn }}
              <i :style="{ background: STATUS_META.bad.color }" />{{ item.bad }}
            </span>
          </div>
        </div>
      </section>
    </div>

    <section v-if="!props.weakOnly" class="ana-card ana-chapter" aria-labelledby="ana-chapter">
      <header class="ana-card__head">
        <h2 id="ana-chapter">章节覆盖</h2>
        <span>按课程时间线分段统计</span>
      </header>
      <div class="ana-chapter__list">
        <div v-for="item in chapterStats" :key="item.chapter" class="ana-chapter__row">
          <span class="ana-chapter__name">{{ item.chapter }}</span>
          <div class="ana-chapter__track"><b :style="{ width: `${item.percent}%` }" /></div>
          <span class="ana-chapter__pct">{{ item.percent }}%</span>
          <span class="ana-chapter__count">{{ item.total }} 个</span>
        </div>
      </div>
    </section>

    <div v-else class="ana-grid ana-grid--weak">
      <section class="ana-card ana-card--weak" aria-labelledby="ana-weak">
        <header class="ana-card__head">
          <h2 id="ana-weak">待加强清单</h2>
          <span>{{ weakNodes.length }} 个待加强</span>
        </header>
        <div class="ana-weak">
          <button
            v-for="node in weakNodes"
            :key="node.id"
            type="button"
            class="ana-weak__row"
            @click="emit('goto', node)"
          >
            <i :style="{ background: STATUS_META[node.status].color }" />
            <span class="ana-weak__name">{{ node.name }}</span>
            <span class="ana-weak__time">{{ formatTime(node.time) }}</span>
            <span class="ana-weak__hits">{{ node.hits }} 次</span>
            <em :style="{ color: STATUS_META[node.status].color }">{{ STATUS_META[node.status].label }}</em>
          </button>
        </div>
        <button type="button" class="ana-card__more" @click="emit('openMap')">
          在知识地图中查看
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M5 12h14M13 6l6 6-6 6" stroke-linecap="round" stroke-linejoin="round" />
          </svg>
        </button>
      </section>
      <section class="ana-plan" aria-labelledby="ana-plan-title">
        <div class="ana-plan__head">
          <h2 id="ana-plan-title">建议先复习</h2>
          <span>点击查看知识点与示例时间点</span>
        </div>
        <div class="ana-plan__list">
          <button
            v-for="(node, index) in planNodes"
            :key="node.id"
            type="button"
            class="ana-plan__card"
            @click="emit('goto', node)"
          >
            <span class="ana-plan__no">{{ String(index + 1).padStart(2, "0") }}</span>
            <div class="ana-plan__body">
              <strong>{{ node.name }}</strong>
              <span>{{ node.quote }}</span>
            </div>
            <span class="ana-plan__meta" :style="{ color: STATUS_META[node.status].color }">
              {{ STATUS_META[node.status].label }} · {{ formatTime(node.time) }}
            </span>
          </button>
        </div>
      </section>
    </div>
  </section>
</template>

<style scoped>
.ana {
  display: flex;
  flex-direction: column;
  gap: 16px;
  min-height: 100%;
  max-width: 1480px;
  margin-inline: auto;
  padding: 22px 26px 26px;
}

.ana-head {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 30px;
  padding-bottom: 15px;
  border-bottom: 1px solid var(--scr-line);
}

.ana-head__title h1 {
  margin: 5px 0 4px;
  color: #16242a;
  font-size: 24px;
  font-weight: 600;
  letter-spacing: 2px;
}

.ana-head__title p {
  margin: 0;
  color: var(--scr-text-dim);
  font-size: 12.5px;
}

.ana-score {
  display: flex;
  flex-direction: column;
  gap: 4px;
  width: 232px;
  flex-shrink: 0;
}

.ana-score > span {
  color: var(--scr-text-faint);
  font-size: 10.5px;
  letter-spacing: 1.2px;
}

.ana-score strong {
  color: var(--scr-accent-deep);
  font-family: "Bahnschrift", Consolas, monospace;
  font-size: 30px;
  font-weight: 500;
  line-height: 1;
  font-variant-numeric: tabular-nums;
}

.ana-score strong em {
  margin-left: 2px;
  font-size: 14px;
  font-style: normal;
}

.ana-score > i {
  display: block;
  height: 4px;
  border-radius: 2px;
  background: #e4eded;
  overflow: hidden;
}

.ana-score > i b {
  display: block;
  height: 100%;
  border-radius: 2px;
  background: linear-gradient(90deg, #17a3a5, #0b6b6d);
}

.ana-score small {
  color: var(--scr-text-faint);
  font-size: 10px;
}

.ana-kpis {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 1px;
  border: 1px solid var(--scr-line);
  border-radius: var(--scr-radius);
  background: var(--scr-line);
  overflow: hidden;
}

.ana-kpis div {
  display: flex;
  flex-direction: column;
  gap: 1px;
  padding: 10px 14px;
  background: rgba(255, 255, 255, 0.94);
}

.ana-kpis span {
  color: var(--scr-text-faint);
  font-size: 10.5px;
}

.ana-kpis strong {
  color: #1d2a2e;
  font-family: "Bahnschrift", Consolas, monospace;
  font-size: 20px;
  font-weight: 500;
  line-height: 1.3;
  font-variant-numeric: tabular-nums;
}

.ana-kpis strong.is-ok { color: var(--scr-green); }
.ana-kpis strong.is-warn { color: var(--scr-amber); }
.ana-kpis strong.is-bad { color: var(--scr-red); }

.ana-kpis small {
  color: var(--scr-text-faint);
  font-size: 10px;
}

.ana-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
  flex: 0 0 auto;
  min-height: 0;
}

.ana-grid--weak { grid-template-columns: minmax(0, 1.2fr) minmax(0, 0.8fr); align-items: start; }
.ana-priorities { display: flex; gap: 8px; flex-shrink: 0; }
.ana-priorities div { min-width: 100px; padding: 8px 14px; border: 1px solid var(--scr-line); border-radius: 8px; background: #fff; }
.ana-priorities span { display: block; color: var(--scr-text-dim); font-size: 12px; }
.ana-priorities strong { color: var(--scr-red); font-size: 24px; }
.ana-priorities div + div strong { color: var(--scr-amber); }
.ana-kpis__link { align-self: start; padding: 0; border: 0; background: transparent; color: var(--scr-accent-deep); font-size: 11px; cursor: pointer; }
.ana-kpis__link:hover { text-decoration: underline; }

.ana-card {
  position: relative;
  display: flex;
  flex-direction: column;
  padding: 15px 16px 16px;
  border: 1px solid var(--scr-line);
  border-radius: var(--scr-radius);
  background: rgba(255, 255, 255, 0.94);
  box-shadow: 0 10px 28px rgba(28, 62, 68, 0.05);
}

.ana-card--weak { border-top: 3px solid var(--scr-red); }

.ana-card__head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 13px;
  padding-bottom: 9px;
  border-bottom: 1px dashed var(--scr-line);
}

.ana-card__head h2 {
  margin: 0;
  color: #16242a;
  font-size: 13.5px;
  font-weight: 600;
  letter-spacing: 1px;
}

.ana-card__head h2::before {
  content: "";
  display: inline-block;
  width: 3px;
  height: 11px;
  margin-right: 7px;
  border-radius: 2px;
  background: var(--scr-accent);
  vertical-align: -1px;
}

.ana-card__head span {
  color: var(--scr-text-faint);
  font-size: 10.5px;
}

/* 掌握分布 */
.ana-dist {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.ana-dist__row {
  display: grid;
  grid-template-columns: 74px minmax(0, 1fr) 74px;
  align-items: center;
  gap: 12px;
}

.ana-dist__label {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  color: var(--scr-text-dim);
  font-size: 13px;
}

.ana-dist__label i {
  width: 7px;
  height: 7px;
  border-radius: 50%;
}

.ana-dist__track {
  height: 8px;
  border-radius: 4px;
  background: #eef3f2;
  overflow: hidden;
}

.ana-dist__track b {
  display: block;
  height: 100%;
  border-radius: 4px;
  transition: width 0.4s ease;
}

.ana-dist__val {
  color: var(--scr-text);
  font-family: "Bahnschrift", Consolas, monospace;
  font-size: 14px;
  text-align: right;
  font-variant-numeric: tabular-nums;
}

.ana-dist__val em {
  margin-left: 6px;
  color: var(--scr-text-faint);
  font-size: 10.5px;
  font-style: normal;
}

.ana-stack {
  display: flex;
  gap: 2px;
  height: 12px;
  margin-top: 22px;
  border-radius: 2px;
  overflow: hidden;
  background: #eef3f2;
}

.ana-stack i { height: 100%; }

.ana-tip {
  margin: 16px 0 0;
  padding-top: 13px;
  border-top: 1px dashed var(--scr-line);
  color: var(--scr-text-faint);
  font-size: 11.5px;
  line-height: 1.9;
}

/* 模块环 */
.ana-rings {
  display: flex;
  align-items: center;
  justify-content: space-around;
  gap: 12px;
  padding: 14px 0 6px;
}

.ana-ring {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 7px;
  min-width: 0;
}

.ana-ring svg {
  width: clamp(88px, 6.6vw, 104px);
  height: clamp(88px, 6.6vw, 104px);
}

.ana-ring text {
  fill: #1d2a2e;
  font-family: "Bahnschrift", Consolas, monospace;
  font-size: 18px;
  font-weight: 500;
}

.ana-ring strong {
  color: var(--scr-text);
  font-size: 12.5px;
  font-weight: 600;
  letter-spacing: 0.8px;
  white-space: nowrap;
}

.ana-ring span {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  color: var(--scr-text-faint);
  font-family: "Bahnschrift", Consolas, monospace;
  font-size: 11px;
}

.ana-ring span i {
  width: 5px;
  height: 5px;
  border-radius: 50%;
}

/* 薄弱清单 */
.ana-weak {
  margin: 0 -4px;
  padding: 0 4px;
}

.ana-weak__row {
  display: grid;
  grid-template-columns: 8px minmax(0, 1fr) 44px 38px 54px;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 10px 5px;
  border: 0;
  border-bottom: 1px solid var(--scr-line-soft);
  background: transparent;
  color: var(--scr-text);
  font: inherit;
  text-align: left;
  cursor: pointer;
  transition: background 0.15s ease;
}

.ana-weak__row:hover { background: rgba(15, 125, 128, 0.05); }

.ana-weak__row > i {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}

.ana-weak__name {
  overflow: hidden;
  font-size: 12.5px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.ana-weak__time,
.ana-weak__hits {
  color: var(--scr-text-faint);
  font-family: "Bahnschrift", Consolas, monospace;
  font-size: 11px;
  font-variant-numeric: tabular-nums;
}

.ana-weak__hits { text-align: right; }

.ana-weak__row em {
  font-size: 11px;
  font-style: normal;
  text-align: right;
  white-space: nowrap;
}

.ana-card__more {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 5px;
  margin-top: 11px;
  padding: 6px;
  border: 1px solid var(--scr-line);
  border-radius: 2px;
  background: #ffffff;
  color: var(--scr-text-dim);
  font: inherit;
  font-size: 11.5px;
  cursor: pointer;
  transition: color 0.16s ease, border-color 0.16s ease;
}

.ana-card__more:hover {
  color: var(--scr-accent-deep);
  border-color: rgba(15, 125, 128, 0.45);
}

/* 复习建议 */
.ana-plan {
  display: flex;
  flex: 0 0 auto;
  flex-direction: column;
  gap: 10px;
  padding: 13px 16px 15px;
  border: 1px solid var(--scr-line);
  border-radius: var(--scr-radius);
  background: rgba(255, 255, 255, 0.9);
}

.ana-plan__head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 10px;
}

.ana-plan__head h2 {
  margin: 0;
  color: #16242a;
  font-size: 13px;
  font-weight: 600;
  letter-spacing: 1px;
}

.ana-plan__head h2::before {
  content: "";
  display: inline-block;
  width: 3px;
  height: 10px;
  margin-right: 7px;
  background: var(--scr-accent);
  vertical-align: -1px;
}

.ana-plan__head span {
  color: var(--scr-text-faint);
  font-size: 10.5px;
}

.ana-plan__list {
  display: grid;
  gap: 12px;
}

.ana-plan__card {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 10px 12px;
  border: 1px solid var(--scr-line);
  border-radius: 2px;
  background: #fbfdfc;
  font: inherit;
  text-align: left;
  cursor: pointer;
  transition: border-color 0.16s ease, background 0.16s ease;
}

.ana-plan__card:hover {
  border-color: rgba(15, 125, 128, 0.4);
  background: #f5faf9;
}

.ana-plan__no {
  color: #c0d0d2;
  font-family: "Bahnschrift", Consolas, monospace;
  font-size: 16px;
  line-height: 1.2;
}

.ana-plan__body {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 3px;
  min-width: 0;
}

.ana-plan__body strong {
  color: var(--scr-text);
  font-size: 12.5px;
  font-weight: 600;
}

.ana-plan__body span {
  display: -webkit-box;
  overflow: hidden;
  color: var(--scr-text-faint);
  font-size: 11px;
  line-height: 1.65;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}

.ana-plan__meta {
  flex-shrink: 0;
  font-family: "Bahnschrift", Consolas, monospace;
  font-size: 10.5px;
  white-space: nowrap;
}

/* 章节 */
.ana-chapter { flex-shrink: 0; }

.ana-chapter__list {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px 26px;
}

.ana-chapter__row {
  display: grid;
  grid-template-columns: 92px minmax(0, 1fr) 34px 34px;
  align-items: center;
  gap: 9px;
}

.ana-chapter__name {
  color: var(--scr-text-dim);
  font-family: "Bahnschrift", Consolas, monospace;
  font-size: 11px;
  font-variant-numeric: tabular-nums;
}

.ana-chapter__track {
  height: 4px;
  border-radius: 2px;
  background: #eef3f2;
  overflow: hidden;
}

.ana-chapter__track b {
  display: block;
  height: 100%;
  border-radius: 2px;
  background: linear-gradient(90deg, #3fb0ad, #0f7d80);
}

.ana-chapter__pct {
  color: var(--scr-text);
  font-family: "Bahnschrift", Consolas, monospace;
  font-size: 11px;
  text-align: right;
  font-variant-numeric: tabular-nums;
}

.ana-chapter__count {
  color: var(--scr-text-faint);
  font-size: 10.5px;
  text-align: right;
}

@media (max-width: 1280px) {
  .ana-chapter__list { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}

@media (max-width: 1080px) {
  .ana-grid { grid-template-columns: minmax(0, 1fr); }
  .ana-head { flex-direction: column; align-items: flex-start; gap: 12px; }
  .ana-score { width: 100%; }
}

@media (max-width: 900px) {
  .ana { padding: 16px 14px 22px; }
  .ana-kpis { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .ana-chapter__list { grid-template-columns: minmax(0, 1fr); }
}
</style>

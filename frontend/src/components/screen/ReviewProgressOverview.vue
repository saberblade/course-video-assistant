<script setup lang="ts">
import { computed } from "vue";
import { ArrowRight, CollectionTag, VideoPlay } from "@element-plus/icons-vue";
import type { Chapter } from "@/types";
import { formatTime } from "@/utils/format";

const props = defineProps<{ chapters: Chapter[]; reviewedIds: string[]; pendingCount: number }>();
const emit = defineEmits<{ resume: [chapter: Chapter]; nav: [key: string] }>();
const reviewed = computed(() => props.reviewedIds.length);
const remaining = computed(() => props.chapters.length - reviewed.value);
const percent = computed(() => props.chapters.length ? Math.round(reviewed.value / props.chapters.length * 100) : 0);
const nextIndex = computed(() => props.chapters.findIndex(c => !props.reviewedIds.includes(c.id)));
const nextChapter = computed(() => props.chapters[nextIndex.value]);
</script>

<template>
  <div class="rp">
    <section class="panel rp-summary" aria-label="本视频复习概览">
      <div class="rp-ring" role="progressbar" :aria-valuenow="percent" aria-valuemin="0" aria-valuemax="100" aria-label="本视频手动复习标记比例" :style="{ background: `conic-gradient(#0f7d80 ${percent}%, #e9efec 0)` }"><div><strong>{{ percent }}<small>%</small></strong><span>手动复习标记</span></div></div>
      <div class="rp-summary-body"><div class="rp-summary-title"><h2>这一段课程，复习到哪里了？</h2><span>{{ reviewed }} / {{ chapters.length }} 节已标记</span></div><dl class="rp-stats"><div><dt>已标记复习</dt><dd>{{ reviewed }}</dd></div><div><dt>尚未标记</dt><dd>{{ remaining }}</dd></div><div><dt>待解决疑问</dt><dd>{{ pendingCount }}</dd></div></dl><p>这里只记录你主动留下的标记，复习内容与标记操作集中在课程导航中。</p></div>
    </section>
    <div class="rp-actions">
      <section class="rp-next">
        <span class="rp-action-icon"><VideoPlay /></span><span class="rp-kicker">NEXT STEP</span>
        <template v-if="nextChapter"><h2>接着复习</h2><p>从尚未标记的章节继续回看</p><div class="rp-next-chapter"><strong>第 {{ String(nextIndex + 1).padStart(2, '0') }} 节</strong><time>{{ formatTime(nextChapter.start_sec) }}–{{ formatTime(nextChapter.end_sec) }}</time></div><button type="button" @click="emit('resume', nextChapter)">回看这一节<ArrowRight /></button></template>
        <template v-else><h2>全部章节已标记</h2><p>需要重温某段内容时，可以直接在导航中查找。</p><button type="button" @click="emit('nav', 'map')">回到课程导航<ArrowRight /></button></template>
        <button v-if="nextChapter" type="button" class="rp-secondary" @click="emit('nav', 'map')">去导航调整复习标记</button>
      </section>
      <section class="panel rp-questions"><span class="rp-action-icon"><CollectionTag /></span><span class="rp-kicker">REVISIT & RESOLVE</span><h2>{{ pendingCount ? '把留下的疑问逐个解决' : '把需要回看的地方留住' }}</h2><p>{{ pendingCount ? '本视频还有待解决的复习线索。到清单里回看原文、提问，弄清楚后再标记结果。' : '看到没想明白的章节，可以在课程导航里添加备注，之后从清单直接回到讲解。' }}</p><button type="button" @click="emit('nav', pendingCount ? 'weak' : 'map')">{{ pendingCount ? '打开待复习清单' : '到导航留下复习线索' }}<ArrowRight /></button></section>
    </div>
  </div>
</template>

<style scoped>
.rp-summary { display: grid; grid-template-columns: 160px 1fr; gap: 35px; align-items: center; padding: 30px 34px; }
.rp-ring { width: 148px; height: 148px; border-radius: 50%; padding: 12px; }
.rp-ring > div { display: flex; flex-direction: column; justify-content: center; align-items: center; width: 100%; height: 100%; border-radius: 50%; background: #fff; }
.rp-ring strong { color: #0f7d80; font: 600 34px 'Bahnschrift',sans-serif; }.rp-ring small { font-size: 16px; }.rp-ring span { margin-top: 5px; font-size: 10px; color: #95a59d; }
.rp-summary-title { display: flex; align-items: center; justify-content: space-between; gap: 18px; }.rp-summary-title h2 { margin: 0; font-size: 19px; color: #2e514a; }.rp-summary-title > span { color: #8da298; font-size: 11px; white-space: nowrap; }
.rp-stats { display: grid; grid-template-columns: repeat(3,1fr); margin: 23px 0 18px; }.rp-stats > div + div { border-left: 1px solid #e9eeeb; padding-left: 25px; }.rp-stats dt { color: #8b9d94; font-size: 11px; }.rp-stats dd { margin: 7px 0 0; color: #3f6757; font: 600 27px 'Bahnschrift',sans-serif; }.rp-summary-body > p { margin: 0; font-size: 11px; color: #94a69b; line-height: 1.8; }
.rp-actions { display: grid; grid-template-columns: 1.15fr 1fr; gap: 21px; margin-top: 22px; }.rp-actions > section { position: relative; min-width: 0; padding: 28px 31px; border-radius: 14px; overflow: hidden; }
.rp-next { color: #fff; border: 1px solid #236d6a; background: linear-gradient(120deg,#175d5e,#277d72); }.rp-actions h2 { position: relative; margin: 11px 0 9px; font-size: 22px; letter-spacing: -.4px; }.rp-actions p { position: relative; margin: 0; font-size: 12px; line-height: 1.9; max-width: 33em; }.rp-next p { color: #acd3c8; }.rp-kicker { position: relative; font-size: 10px; font-weight: 650; letter-spacing: 1.2px; color: #a5d4c5; }
.rp-action-icon { position: absolute; top: 25px; right: 28px; width: 72px; height: 72px; opacity: .08; pointer-events: none; }
.rp-next-chapter { display: flex; align-items: center; gap: 16px; margin: 20px 0; }.rp-next-chapter strong { font-size: 17px; }.rp-next-chapter time { padding: 4px 9px; border-radius: 5px; background: #ffffff14; color: #c3e2d5; font: 12px Consolas,monospace; }
.rp-actions button { position: relative; display: inline-flex; align-items: center; gap: 13px; margin-top: 24px; padding: 9px 14px; border: 1px solid #cedfd6; border-radius: 7px; background: #fff; color: #3b7762; font: inherit; font-size: 12px; cursor: pointer; }.rp-actions button svg { width: 14px; }.rp-next-chapter + button { margin-top: 0; }.rp-next .rp-secondary { display: block; border: none; padding: 0; background: none; color: #b3d7cb; font-size: 11px; margin-top: 16px; }.rp-actions button:focus-visible { outline: 3px solid #84b6a4; outline-offset: 3px; }
.rp-questions .rp-kicker { color: #85a393; }.rp-questions h2 { color: #385f4e; }.rp-questions p { color: #879c8e; }.rp-questions .rp-action-icon { color: #438568; }
@media (max-width:900px) { .rp-summary { grid-template-columns: 130px 1fr; padding: 24px; gap: 24px; }.rp-ring { width: 125px; height: 125px; }.rp-summary-title { display: block; }.rp-summary-title > span { display: block; margin-top: 7px; }.rp-summary-title h2 { font-size: 17px; }.rp-actions { grid-template-columns: 1fr 1fr; }.rp-actions > section { padding: 24px; }.rp-actions h2 { font-size: 20px; } }
@media (max-width:600px) { .rp-summary { grid-template-columns: 1fr; gap: 20px; padding: 24px; }.rp-ring { justify-self: center; width: 130px; height: 130px; }.rp-stats > div + div { padding-left: 16px; }.rp-stats { margin-top: 20px; }.rp-actions { grid-template-columns: 1fr; gap: 15px; }.rp-actions > section { padding: 24px; }.rp-summary-title h2 { font-size: 17px; } }
</style>

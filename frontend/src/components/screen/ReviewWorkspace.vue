<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ArrowRight, CollectionTag, Document, Refresh, Search, VideoCamera } from "@element-plus/icons-vue";
import { ElMessage, ElMessageBox } from "element-plus";
import { api } from "@/api";
import { toApiError } from "@/api/http";
import { useReviewRecords, type ReviewRecord } from "@/composables/useReviewRecords";
import { useCurrentCourse } from "@/composables/useCurrentCourse";
import type { Chapter, TranscriptSegment, Video } from "@/types";
import { formatDate, formatDuration, formatTime } from "@/utils/format";
import "@/styles/review-workspace.css";
import ChapterRouteMap from "./ChapterRouteMap.vue";
import ReviewProgressOverview from "./ReviewProgressOverview.vue";

const props = defineProps<{ view: "map" | "analysis" | "weak" }>();
const emit = defineEmits<{ nav: [key: string] }>();
const router = useRouter();
const route = useRoute();
const store = useReviewRecords();
const { records, storageError, canSave, saveState } = store;
const videos = ref<Video[]>([]);
const total = ref(0);
const loading = ref(false);
const catalogError = ref("");
const { selectedId } = useCurrentCourse();
const video = ref<Video>();
const chapters = ref<Chapter[]>([]);
const contentLoading = ref(false);
const contentError = ref("");
const selectedChapter = ref("");
const atlasOpen = ref(false);
const chapterContent = ref<HTMLElement>();
const todoKeyword = ref("");
const todoFilter = ref<"open" | "done" | "all">("open");
const noteDialog = ref(false);
const noteDraft = ref("");
const noteTarget = ref<{ video: Video; chapter: Chapter } | { record: ReviewRecord }>();
const showSources = ref(false);
const sourceLoading = ref(false);
const sourceError = ref("");
const transcript = ref<TranscriptSegment[] | null>(null);
const openingKey = ref("");
let request = 0;
let disposed = false;
let catalogOffset = 0;
let catalogLoaded = false;

const titles = { map: "课程知识导航", analysis: "复习进度", weak: "待复习清单" };
const subtitles = {
  map: "沿着课程时间线，找到你想回看的那一段。",
  analysis: "查看本视频的复习概况，决定下一步从哪里继续。",
  weak: "把没想明白的地方留下来，回看、提问，再逐个解决。",
};
const activeChapter = computed(() => chapters.value.find(c => c.id === selectedChapter.value));
const currentKeys = computed(() => new Set(video.value ? chapters.value.map(c => `${video.value!.id}:${video.value!.attempt}:${c.id}`) : []));
const currentRecords = computed(() => records.value.filter(r => currentKeys.value.has(r.key)));
const reviewedIds = computed(() => currentRecords.value.filter(r => r.reviewed).map(r => r.chapterId));
const savedIds = computed(() => currentRecords.value.filter(r => r.saved && !r.resolved).map(r => r.chapterId));
const activeNumber = computed(() => String(chapters.value.findIndex(c => c.id === selectedChapter.value) + 1).padStart(2, "0"));
const activeIndex = computed(() => chapters.value.findIndex(c => c.id === selectedChapter.value));
const currentPending = computed(() => currentRecords.value.filter(r => r.saved && !r.resolved).length);
const saved = computed(() => records.value.filter(r => r.saved).sort((a, b) => b.updatedAt.localeCompare(a.updatedAt)));
const openCount = computed(() => saved.value.filter(r => !r.resolved).length);
const doneCount = computed(() => saved.value.filter(r => r.resolved).length);
const todos = computed(() => saved.value.filter(r => {
  const statusMatch = todoFilter.value === "all" || (todoFilter.value === "done" ? r.resolved : !r.resolved);
  return statusMatch && `${r.videoTitle} ${r.text} ${r.note}`.toLowerCase().includes(todoKeyword.value.trim().toLowerCase());
}));
const sources = computed(() => activeChapter.value?.segment_ids.map(id => transcript.value?.find(s => s.id === id)).filter((s): s is TranscriptSegment => Boolean(s)) ?? []);
const currentState = (chapter: Chapter) => video.value ? store.find(video.value, chapter) : undefined;
const videoStatusNames: Record<Video["status"], string> = { ready: "可以复习", queued: "排队中", transcribing: "正在转写", indexing: "正在整理", failed: "处理失败" };

async function loadVideos(more = false) {
  if (loading.value) return;
  loading.value = true;
  catalogError.value = "";
  try {
    const result = await api.listVideos(100, more ? catalogOffset : 0);
    if (disposed) return;
    catalogLoaded = true;
    total.value = result.total;
    catalogOffset = more ? catalogOffset + result.items.length : result.items.length;
    videos.value = more ? [...videos.value, ...result.items.filter(v => !videos.value.some(old => old.id === v.id))] : result.items;
    if (!more && selectedId.value && !videos.value.some(v => v.id === selectedId.value)) {
      const requested = await api.getVideo(selectedId.value).catch(() => null);
      if (disposed) return;
      if (requested?.status === "ready") videos.value.push(requested);
    }
    const available = videos.value.filter(v => v.status === "ready");
    if (!available.some(v => v.id === selectedId.value)) selectedId.value = available[0]?.id ?? "";
    else if (!more) { syncSelectionQuery(); void loadContent(); }
  } catch (error) { catalogError.value = toApiError(error).message; }
  finally { loading.value = false; }
}
async function loadContent() {
  const id = selectedId.value;
  const ticket = ++request;
  video.value = undefined;
  chapters.value = [];
  transcript.value = null;
  selectedChapter.value = "";
  contentError.value = "";
  showSources.value = false;
  atlasOpen.value = false;
  sourceLoading.value = false;
  if (!id) { contentLoading.value = false; return; }
  contentLoading.value = true;
  try {
    const [detail, summary] = await Promise.all([api.getVideo(id), api.getSummary(id)]);
    if (disposed || ticket !== request) return;
    video.value = detail;
    if (!videos.value.some(item => item.id === detail.id)) videos.value.push(detail);
    chapters.value = summary.chapters;
    selectedChapter.value = summary.chapters[0]?.id ?? "";
  } catch (error) { if (ticket === request && !disposed) contentError.value = toApiError(error).message; }
  finally { if (ticket === request && !disposed) contentLoading.value = false; }
}
function syncSelectionQuery() {
  if (route.name !== "screen" || (route.query.video ?? "") === selectedId.value) return;
  const query = { ...route.query };
  if (selectedId.value) query.video = selectedId.value;
  else delete query.video;
  void router.replace({ query });
}
watch(selectedId, () => {
  syncSelectionQuery();
  void loadContent();
});
watch(selectedChapter, () => {
  showSources.value = false;
  void nextTick(() => chapterContent.value?.closest(".el-drawer__body")?.scrollTo({ top: 0 }));
});
watch(() => props.view, value => {
  if (value !== "map") atlasOpen.value = false;
  if (value !== "weak" && !catalogLoaded) void loadVideos();
});
onMounted(() => { void store.refresh(); if (props.view !== "weak") void loadVideos(); });
onBeforeUnmount(() => { disposed = true; request++; });

function openVideo(id: string, time = 0, question = false) {
  void router.push({ name: "video-detail", params: { id }, query: { from: "screen", view: props.view, t: String(time), ...(question ? { panel: "question" } : {}) } });
}
function toggleReviewed(chapter: Chapter) {
  if (!canSave.value) { ElMessage.info("请先登录，再保存复习标记。"); return; }
  if (video.value) store.update(video.value, chapter, { reviewed: !currentState(chapter)?.reviewed });
}
function openChapter(chapter: Chapter) {
  selectedChapter.value = chapter.id;
  atlasOpen.value = true;
}
function openNote(chapter: Chapter) {
  if (!canSave.value) { ElMessage.info("请先登录，再添加备注。"); return; }
  if (!video.value) return;
  noteTarget.value = { video: video.value, chapter };
  noteDraft.value = currentState(chapter)?.note ?? "";
  noteDialog.value = true;
}
function editNote(record: ReviewRecord) {
  noteTarget.value = { record };
  noteDraft.value = record.note;
  noteDialog.value = true;
}
function saveNote() {
  if (!canSave.value) return;
  const target = noteTarget.value;
  if (!target) return;
  if ("record" in target) store.edit(target.record.key, { note: noteDraft.value.trim() });
  else store.update(target.video, target.chapter, { saved: true, resolved: false, note: noteDraft.value.trim() });
  noteDialog.value = false;
  ElMessage.success(storageError.value ? "本次记录已暂存，请留意存储提示" : "复习线索已保存");
}
async function toggleSources() {
  showSources.value = !showSources.value;
  if (!showSources.value || transcript.value || !video.value || sourceLoading.value) return;
  const id = video.value.id;
  const ticket = request;
  sourceError.value = "";
  sourceLoading.value = true;
  try {
    const result = await api.getTranscript(id);
    if (!disposed && ticket === request) transcript.value = result.segments;
  } catch (error) { if (ticket === request) sourceError.value = toApiError(error).message; }
  finally { if (ticket === request) sourceLoading.value = false; }
}
async function openRecord(record: ReviewRecord, question = false) {
  if (openingKey.value) return;
  openingKey.value = record.key;
  try {
    const detail = await api.getVideo(record.videoId);
    if (detail.status !== "ready" || detail.attempt !== record.attempt) {
      ElMessage.warning("来源视频的处理版本已变化，请在课程导航中查看最新内容。这条本地备注仍会保留。");
      return;
    }
    openVideo(record.videoId, record.start, question);
  } catch { ElMessage.warning("暂时无法打开来源视频。记录仍保留，可稍后重试或从清单移除。"); }
  finally { openingKey.value = ""; }
}
async function removeRecord(record: ReviewRecord) {
  try {
    await ElMessageBox.confirm("从本地清单移除这条复习线索？课程视频和独立的已复习标记会保留。", "移出待复习清单", { confirmButtonText: "移出清单", cancelButtonText: "取消" });
    store.remove(record.key);
  } catch { /* cancelled */ }
}
</script>

<template>
  <section class="rw" :class="{ 'rw--route': view === 'map' }" :aria-label="titles[view]">
    <header class="rw-heading">
      <div><span class="section-kicker">{{ view === 'map' ? 'COURSE ATLAS' : view === 'analysis' ? 'YOUR REVIEW' : 'REVISIT & RESOLVE' }}</span><h1>{{ titles[view] }}</h1><p>{{ subtitles[view] }}</p></div>
    </header>
    <el-alert v-if="storageError" :title="storageError" type="warning" :closable="false" show-icon class="rw-alert" />
    <p v-else-if="saveState === 'saving'" class="rw-save-hint" aria-live="polite">正在保存复习记录…</p>
    <p v-else-if="saveState === 'saved'" class="rw-save-hint is-saved" aria-live="polite">复习记录已保存到账号</p>

    <template v-if="view !== 'weak'">
      <section class="rw-course panel" aria-label="选择课程视频">
        <span class="rw-course-icon"><VideoCamera /></span>
        <div class="rw-course-select"><label for="review-video">当前课程视频</label><el-select id="review-video" v-model="selectedId" class="rw-video-select" popper-class="rw-video-menu" aria-label="选择课程视频" filterable :placeholder="loading ? '正在读取课程…' : '搜索或选择课程视频'" :disabled="!videos.some(v => v.status === 'ready')" no-match-text="没有匹配的课程视频" no-data-text="暂无可复习的课程" :show-arrow="true"><el-option v-for="item in videos" :key="item.id" :value="item.id" :label="item.title" :disabled="item.status !== 'ready'"><div class="rw-video-option"><span class="rw-video-option-icon"><VideoCamera /></span><div class="rw-video-option-copy"><strong :title="item.title">{{ item.title }}</strong><small>{{ formatDuration(item.duration_sec) }}<i />{{ videoStatusNames[item.status] }}</small></div><span class="rw-video-option-state" :class="{ 'is-ready': item.status === 'ready' }">{{ item.id === selectedId ? '当前课程' : videoStatusNames[item.status] }}</span></div></el-option></el-select></div>
        <span v-if="video" class="rw-course-duration">{{ formatDuration(video.duration_sec) }} · {{ chapters.length }} 个章节</span>
        <el-button :loading="loading" @click="loadVideos()"><el-icon><Refresh /></el-icon>刷新课程</el-button>
        <el-button v-if="videos.length < total" :loading="loading" @click="loadVideos(true)">加载更多课程</el-button>
      </section>
      <el-alert v-if="catalogError" :title="'课程读取失败：' + catalogError" type="error" :closable="false" show-icon class="rw-alert" />
      <div v-if="catalogError && !videos.length" class="panel rw-empty"><Document /><h2>暂时无法读取课程列表</h2><p>课程内容不会因此丢失，恢复连接后可以继续复习。</p><el-button :loading="loading" @click="loadVideos()">重新读取课程</el-button></div>
      <div v-else-if="contentLoading || (loading && !selectedId)" class="panel rw-empty"><el-skeleton :rows="5" animated /></div>
      <div v-else-if="contentError" class="panel rw-empty"><Document /><h2>暂时无法读取章节</h2><p>{{ contentError }}</p><el-button @click="loadContent">重新加载</el-button></div>
      <div v-else-if="!video || !chapters.length" class="panel rw-empty"><CollectionTag /><h2>{{ videos.length ? '等待课程处理完成' : '从第一段课程开始' }}</h2><p>上传并处理视频后，这里会按真实章节整理复习入口。</p><el-button type="primary" @click="emit('nav', 'library')">前往我的课程<el-icon><ArrowRight /></el-icon></el-button></div>

      <template v-else-if="view === 'map'">
        <ChapterRouteMap :chapters="chapters" :reviewed-ids="reviewedIds" :saved-ids="savedIds" :active-id="atlasOpen ? selectedChapter : ''" @open="openChapter" />
        <el-drawer v-model="atlasOpen" :title="`第 ${activeNumber} 节 · 章节原文`" size="min(520px, 100vw)" append-to-body class="cr-detail-drawer" :close-on-click-modal="true">
          <article v-if="activeChapter" ref="chapterContent" class="rw-chapter cr-detail-content">
            <div class="rw-chapter-top"><span class="rw-pill">{{ formatTime(activeChapter.start_sec) }} — {{ formatTime(activeChapter.end_sec) }}</span><span class="rw-muted">提取式 · 课程原句</span></div>
            <h2>这一节讲了什么</h2><p class="rw-chapter-copy">{{ activeChapter.text }}</p>
            <div class="rw-chapter-actions"><el-button type="primary" @click="openVideo(video.id, activeChapter.start_sec)">回看这段讲解<el-icon><ArrowRight /></el-icon></el-button><el-button @click="openVideo(video.id, activeChapter.start_sec, true)">向课程提问</el-button></div>
            <div class="rw-mark-box">
              <div><strong>你的复习标记</strong><p>{{ canSave ? '按自己的复习情况标记，疑问可以留到下次回看。' : '登录后可以保存标记与备注。' }}</p></div>
              <div class="rw-mark-actions"><el-button :disabled="!canSave" :type="currentState(activeChapter)?.reviewed ? 'success' : 'default'" :aria-pressed="Boolean(currentState(activeChapter)?.reviewed)" @click="toggleReviewed(activeChapter)">{{ currentState(activeChapter)?.reviewed ? '已复习 · 撤销标记' : '标记已复习' }}</el-button><el-button :disabled="!canSave" @click="openNote(activeChapter)">{{ currentState(activeChapter)?.saved ? '编辑复习线索' : '加入待复习' }}</el-button></div>
              <p v-if="currentState(activeChapter)?.note" class="rw-saved-note">我的备注：{{ currentState(activeChapter)?.note }}</p>
            </div>
            <button class="rw-source-toggle" :aria-expanded="showSources" @click="toggleSources">{{ showSources ? '收起来源原文' : `查看 ${activeChapter.segment_ids.length} 条来源原文` }}</button>
            <div v-if="showSources" class="rw-sources"><p v-if="sourceLoading">正在读取原文…</p><div v-else-if="sourceError"><p>{{ sourceError }}</p><el-button @click="showSources = false; toggleSources()">重试读取</el-button></div><template v-else><button v-for="source in sources" :key="source.id" @click="openVideo(video.id, source.start_sec)"><time>{{ formatTime(source.start_sec) }}</time><span>{{ source.text }}</span><ArrowRight /></button><p v-if="!sources.length">当前来源片段暂不可用，请打开课程核对。</p></template></div>
            <nav class="cr-detail-pager" aria-label="切换章节"><el-button :disabled="activeIndex <= 0" @click="selectedChapter = chapters[activeIndex - 1]!.id">上一节</el-button><span>{{ activeNumber }} / {{ chapters.length }}</span><el-button :disabled="activeIndex >= chapters.length - 1" @click="selectedChapter = chapters[activeIndex + 1]!.id">下一节</el-button></nav>
          </article>
        </el-drawer>
      </template>

      <div v-else-if="!canSave" class="panel rw-empty"><CollectionTag /><h2>复习记录暂不可用</h2><p>请先登录账号，再保存复习标记与备注。</p><el-button type="primary" @click="emit('nav', 'map')">查看课程章节</el-button></div>
      <template v-else>
        <ReviewProgressOverview :chapters="chapters" :reviewed-ids="reviewedIds" :pending-count="currentPending" @resume="openVideo(video.id, $event.start_sec)" @nav="emit('nav', $event)" />
      </template>
    </template>

    <div v-else-if="!canSave" class="panel rw-empty"><CollectionTag /><h2>待复习清单暂不可用</h2><p>请先登录账号，再查看自己留下的复习线索。</p><el-button type="primary" @click="emit('nav', 'library')">前往我的课程</el-button></div>
    <template v-else>
      <section class="rw-todo-summary"><div><CollectionTag /><span>待解决的线索<strong>{{ openCount }}</strong></span></div><p>每条记录都连着一段讲解。先处理你自己留下的问题。</p><span class="rw-resolved-total">已解决 {{ doneCount }} 条</span></section>
      <div class="rw-todo-tools"><div class="rw-filters" aria-label="筛选复习线索"><button v-for="filter in (['open', 'done', 'all'] as const)" :key="filter" :aria-pressed="todoFilter === filter" :class="{ 'is-active': todoFilter === filter }" @click="todoFilter = filter">{{ filter === 'open' ? `待解决 ${openCount}` : filter === 'done' ? `已解决 ${doneCount}` : `全部 ${saved.length}` }}</button></div><el-input v-model="todoKeyword" placeholder="搜索课程、原文或我的备注" clearable aria-label="搜索复习线索"><template #prefix><Search /></template></el-input></div>
      <div v-if="!todos.length" class="panel rw-empty"><CollectionTag /><h2>{{ todoKeyword ? '没有匹配的复习线索' : todoFilter === 'done' ? '还没有已解决的记录' : openCount === 0 && doneCount > 0 && todoFilter === 'open' ? '当前的疑问都已解决' : '把想回看的地方留在这里' }}</h2><p>{{ todoKeyword ? '试试课程名称或其他关键词。' : '在课程知识导航中选择章节，点击“加入待复习”，可以附上自己的疑问。' }}</p><el-button v-if="!todoKeyword" type="primary" @click="emit('nav', 'map')">前往课程知识导航</el-button></div>
      <div v-else class="rw-todo-list"><article v-for="record in todos" :key="record.key" class="panel rw-todo-card"><div class="rw-section-row"><span class="rw-state" :class="{ 'is-done': record.resolved }">{{ record.resolved ? '已解决' : '待解决' }}</span><span class="rw-muted">{{ formatDate(record.updatedAt) }}</span></div><h2>{{ record.videoTitle }}</h2><div class="rw-todo-time">{{ formatTime(record.start) }} — {{ formatTime(record.end) }} · 第 {{ record.attempt }} 次处理</div><p class="rw-todo-note">{{ record.note || '留给下一次复习的片段，回看后可以补充自己的理解。' }}</p><blockquote>{{ record.text }}</blockquote><div class="rw-todo-actions"><el-button type="primary" :loading="openingKey === record.key" @click="openRecord(record)">回到这段讲解</el-button><el-button @click="openRecord(record, true)">向课程提问</el-button><el-button @click="store.edit(record.key, { resolved: !record.resolved })">{{ record.resolved ? '重新待复习' : '标记已解决' }}</el-button><el-button text @click="editNote(record)">编辑备注</el-button><el-button text class="rw-remove" @click="removeRecord(record)">移出清单</el-button></div></article></div>
    </template>
    <el-dialog v-model="noteDialog" title="留下复习线索" width="min(540px, calc(100vw - 32px))" append-to-body :close-on-click-modal="false"><p class="rw-dialog-hint">写下哪里没理解，或下次想重点回看什么。备注可留空。</p><el-input v-model="noteDraft" type="textarea" :rows="4" maxlength="500" show-word-limit placeholder="例如：这里为什么要先调整工程参数？" aria-label="我的复习备注" /><template #footer><el-button @click="noteDialog = false">取消</el-button><el-button type="primary" @click="saveNote">保存复习线索</el-button></template></el-dialog>
  </section>
</template>

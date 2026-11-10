import { computed, ref, type Ref } from "vue";

/** 滚轮平移画布，缩放由显式控件触发；拖动与点击分别处理。 */
export function usePanZoom(viewport: Ref<HTMLElement | undefined>, content: Ref<HTMLElement | undefined>) {
  const scale = ref(1);
  const x = ref(16);
  const y = ref(16);
  const dragging = ref(false);
  const minimum = 0.2;
  const maximum = 1.8;
  let overview = false;
  let suppressClickUntil = 0;
  let drag: { id: number; clientX: number; clientY: number; x: number; y: number; moved: boolean } | undefined;
  const transform = computed(() => `translate(${x.value}px, ${y.value}px) scale(${scale.value})`);
  const clamp = (value: number, low: number, high: number) => Math.min(high, Math.max(low, value));

  function constrain() {
    const view = viewport.value;
    const world = content.value;
    if (!view || !world) return;
    const w = world.offsetWidth * scale.value;
    const h = world.offsetHeight * scale.value;
    x.value = w <= view.clientWidth - 32 ? (view.clientWidth - w) / 2 : clamp(x.value, view.clientWidth - w - 24, 24);
    y.value = h <= view.clientHeight - 32 ? (view.clientHeight - h) / 2 : clamp(y.value, view.clientHeight - h - 24, 24);
  }
  function zoomTo(value: number, anchorX?: number, anchorY?: number) {
    const view = viewport.value;
    if (!view) return;
    const ax = anchorX ?? view.clientWidth / 2;
    const ay = anchorY ?? view.clientHeight / 2;
    const next = clamp(value, minimum, maximum);
    const ratio = next / scale.value;
    x.value = ax - (ax - x.value) * ratio;
    y.value = ay - (ay - y.value) * ratio;
    scale.value = next;
    overview = false;
    constrain();
  }
  function reset() {
    overview = false;
    scale.value = 1;
    x.value = 16;
    y.value = 16;
    constrain();
  }
  function fit() {
    const view = viewport.value;
    const world = content.value;
    if (!view || !world) return;
    overview = true;
    scale.value = clamp(Math.min((view.clientWidth - 32) / world.offsetWidth, (view.clientHeight - 32) / world.offsetHeight, 1), minimum, maximum);
    x.value = (view.clientWidth - world.offsetWidth * scale.value) / 2;
    y.value = (view.clientHeight - world.offsetHeight * scale.value) / 2;
    constrain();
  }
  function layoutChanged(resetView = false) {
    if (resetView) reset();
    else if (overview) fit();
    else constrain();
  }
  function onWheel(event: WheelEvent) {
    const view = viewport.value;
    if (!view) return;
    if (event.ctrlKey || event.metaKey) return;
    event.preventDefault();
    const multiplier = event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? view.clientHeight : 1;
    overview = false;
    if (event.shiftKey) {
      x.value -= (event.deltaX || event.deltaY) * multiplier;
    } else {
      x.value -= event.deltaX * multiplier;
      y.value -= event.deltaY * multiplier;
    }
    constrain();
  }
  function onPointerDown(event: PointerEvent) {
    if (drag || (event.pointerType === "mouse" && event.button !== 0 && event.button !== 1)) return;
    // 新一次按下代表用户有意点击，不应被上一次拖动的 click 抑制影响。
    suppressClickUntil = 0;
    if (event.button === 1) event.preventDefault();
    drag = { id: event.pointerId, clientX: event.clientX, clientY: event.clientY, x: x.value, y: y.value, moved: false };
    if (!(event.target instanceof Element && event.target.closest("button"))) viewport.value?.focus({ preventScroll: true });
  }
  function onPointerMove(event: PointerEvent) {
    if (!drag || drag.id !== event.pointerId) return;
    const dx = event.clientX - drag.clientX;
    const dy = event.clientY - drag.clientY;
    if (!drag.moved && Math.hypot(dx, dy) < 5) return;
    if (!drag.moved) {
      drag.moved = true;
      dragging.value = true;
      viewport.value?.setPointerCapture(event.pointerId);
    }
    event.preventDefault();
    overview = false;
    x.value = drag.x + dx;
    y.value = drag.y + dy;
    constrain();
  }
  function endPointer(event: PointerEvent) {
    if (!drag || drag.id !== event.pointerId) return;
    if (drag.moved) suppressClickUntil = performance.now() + 350;
    drag = undefined;
    dragging.value = false;
    if (viewport.value?.hasPointerCapture(event.pointerId)) viewport.value.releasePointerCapture(event.pointerId);
  }
  function captureClick(event: MouseEvent) {
    if (event.detail !== 0 && performance.now() < suppressClickUntil) {
      suppressClickUntil = 0;
      event.preventDefault();
      event.stopImmediatePropagation();
    }
  }
  function reveal(element: HTMLElement) {
    const view = viewport.value;
    if (!view) return;
    const box = element.getBoundingClientRect();
    const frame = view.getBoundingClientRect();
    if (box.left >= frame.left + 10 && box.right <= frame.right - 10 && box.top >= frame.top + 10 && box.bottom <= frame.bottom - 10) return;
    overview = false;
    x.value += frame.left + frame.width / 2 - (box.left + box.width / 2);
    y.value += frame.top + frame.height / 2 - (box.top + box.height / 2);
    constrain();
  }
  function onKeydown(event: KeyboardEvent) {
    const offsets: Record<string, [number, number]> = { ArrowLeft: [90, 0], ArrowRight: [-90, 0], ArrowUp: [0, 90], ArrowDown: [0, -90] };
    const offset = offsets[event.key];
    if (offset) {
      event.preventDefault(); overview = false; x.value += offset[0]; y.value += offset[1]; constrain();
    } else if (event.key === "+" || event.key === "=") { event.preventDefault(); zoomTo(scale.value * 1.2); }
    else if (event.key === "-") { event.preventDefault(); zoomTo(scale.value / 1.2); }
    else if (event.key === "0") { event.preventDefault(); reset(); }
  }
  return { scale, transform, dragging, zoomTo, reset, fit, layoutChanged, reveal, onWheel, onPointerDown, onPointerMove, endPointer, captureClick, onKeydown };
}

<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from "vue";
import AccountMenu from "@/components/AccountMenu.vue";

const props = defineProps<{ active: string }>();
const emit = defineEmits<{ nav: [key: string]; exit: [] }>();

const menus = [
  { key: "map", name: "课程知识导航" },
  { key: "library", name: "我的课程" },
  { key: "analysis", name: "复习进度" },
  { key: "weak", name: "待复习清单" },
];

const clock = ref("");
let timer = 0;

function tick() {
  const now = new Date();
  clock.value = [now.getHours(), now.getMinutes(), now.getSeconds()]
    .map((n) => String(n).padStart(2, "0"))
    .join(":");
}

onMounted(() => {
  tick();
  timer = window.setInterval(tick, 1000);
});

onBeforeUnmount(() => window.clearInterval(timer));
</script>

<template>
  <header class="scr-topbar">
    <RouterLink to="/" class="scr-brand" aria-label="返回课迹首页">
      <img class="brand-emblem" src="/bupt-emblem.png" alt="北京邮电大学校徽" width="42" height="42" />
      <span class="scr-brand__name">课迹</span>
      <span class="scr-brand__divider" />
      <span class="scr-brand__desc">课程知识云台</span>
    </RouterLink>

    <nav class="scr-menu" aria-label="知识云台">
      <button
        v-for="item in menus"
        :key="item.key"
        type="button"
        class="scr-menu__item"
        :class="{ 'is-active': item.key === props.active }"
        :aria-current="item.key === props.active ? 'page' : undefined"
        @click="emit('nav', item.key)"
      >
        {{ item.name }}
      </button>
    </nav>

    <div class="scr-topbar__right">
      <span class="scr-clock">{{ clock }}</span>
      <AccountMenu />
      <button type="button" class="scr-topbar__link" @click="emit('exit')">返回首页</button>
    </div>
  </header>
</template>

<script setup lang="ts">
import { computed } from "vue";
import { useRoute } from "vue-router";
import AppHeader from "@/components/AppHeader.vue";
import GlobalAssistant from "@/components/GlobalAssistant.vue";

const route = useRoute();
const landing = computed(() => route.name === "home");
</script>

<template>
  <div class="app-shell">
    <AppHeader v-if="landing" />
    <RouterView :key="$route.name === 'screen' ? $route.path : $route.fullPath" />
    <footer v-if="landing" class="app-footer">
      <div class="container">课迹 · 让课程复习回到原文与时间点</div>
    </footer>
    <GlobalAssistant />
  </div>
</template>

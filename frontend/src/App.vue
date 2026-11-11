<script setup lang="ts">
import { computed } from "vue";
import { useRoute } from "vue-router";
import AppHeader from "@/components/AppHeader.vue";
import GlobalAssistant from "@/components/GlobalAssistant.vue";
import { sessionState } from "@/stores/session";
import { isMock } from "@/api/http";

const route = useRoute();
const landing = computed(() => route.name === "home");
</script>

<template>
  <div class="app-shell">
    <AppHeader v-if="landing" />
    <RouterView v-if="isMock || !route.meta.requiresAuth || sessionState.user.value" :key="`${sessionState.revision.value}:${$route.name === 'screen' ? $route.path : $route.fullPath}`" />
    <footer v-if="landing" class="app-footer">
      <div class="container">课迹 · 让课程复习回到原文与时间点</div>
    </footer>
    <GlobalAssistant v-if="route.name !== 'login'" :key="sessionState.revision.value" />
  </div>
</template>

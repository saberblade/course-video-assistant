<template>
  <header class="app-header">
    <div class="container app-header__inner">
      <RouterLink to="/" class="brand" aria-label="返回课迹首页">
        <img class="brand-emblem" src="/bupt-emblem.png" alt="北京邮电大学校徽" width="44" height="44" />
        <span class="brand__name">课迹</span>
        <span class="brand__divider" />
        <span class="brand__desc">课程视频复习助手</span>
      </RouterLink>
    </div>
  </header>
</template>

<style scoped>
.app-header {
  height: 72px;
  background: rgba(255, 255, 255, 0.96);
  border-bottom: 1px solid var(--line);
}
.app-header__inner { height: 100%; display: flex; align-items: center; }
.brand { display: flex; align-items: center; color: var(--ink); text-decoration: none; flex-shrink: 0; }
.brand__name { margin-left: 11px; font-size: 24px; font-weight: 750; letter-spacing: 2px; }
.brand__divider { width: 1px; height: 18px; background: var(--line); margin: 0 14px; }
.brand__desc { color: var(--muted); font-size: 15px; }
@media (max-width: 760px) {
  .app-header { height: 64px; }
  .brand__divider, .brand__desc { display: none; }
  .brand__name { margin-left: 7px; font-size: 22px; }
  .brand-emblem { width: 38px; height: 38px; }
}
</style>

<script setup lang="ts">
import { ArrowRight, ChatDotRound, Reading, VideoCamera } from "@element-plus/icons-vue";
</script>

<template>
  <main class="landing">
    <div class="container landing__inner">
      <header class="landing__intro">
        <span class="landing__eyebrow"><VideoCamera aria-hidden="true" /> 课迹 · 课程知识云台</span>
        <h1>课程视频<span>复习助手</span></h1>
        <p>把录课变成可以按章节浏览、围绕原文提问的复习资料。</p>
      </header>

      <section class="landing__features" aria-label="功能介绍">
        <article class="feature feature--chapters">
          <svg class="feature__map" viewBox="0 0 260 188" aria-hidden="true">
            <path d="M20 128 54 46 150 24 229 56 246 135 154 174 80 161Z M54 46 80 161 M150 24 154 174 M229 56 154 174" />
            <path class="feature__map-route" d="M61 113 103 78 153 114 206 71" />
            <circle cx="61" cy="113" r="5" /><circle cx="103" cy="78" r="5" />
            <circle cx="153" cy="114" r="5" /><circle cx="206" cy="71" r="5" />
          </svg>
          <div class="feature__content">
            <span class="feature__label"><Reading aria-hidden="true" /> 章节提要</span>
            <h2>按时间梳理课程重点</h2>
            <p>上传中文课程视频后，按章节查看提要和转写，快速找到想复习的片段。</p>
          </div>
        </article>

        <article class="feature feature--citations">
          <div class="feature__content">
            <span class="feature__label"><ChatDotRound aria-hidden="true" /> 原文问答</span>
            <h2>带着问题回到讲解</h2>
            <p>围绕当前课程提问。找到相关原文时，点击回答里的引用即可回到讲解位置。</p>
          </div>
          <ol class="feature__steps" aria-label="复习流程">
            <li>上传课程</li>
            <li>浏览提要</li>
            <li>提问定位</li>
          </ol>
        </article>
      </section>

      <RouterLink to="/screen" class="landing__enter">
        进入知识云台 <ArrowRight aria-hidden="true" />
      </RouterLink>
    </div>
  </main>
</template>

<style scoped>
.landing {
  display: grid;
  flex: 1;
  align-items: center;
  padding: clamp(28px, 5vh, 64px) 0 clamp(30px, 6vh, 70px);
  background: radial-gradient(ellipse at 50% 0, #e2f2ef 0, transparent 75%), linear-gradient(#f0f7f6, #fff);
}

.landing__inner { max-width: 1024px; text-align: center; }
.landing__eyebrow {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  padding: 5px 12px;
  border: 1px solid #cde1df;
  border-radius: 99px;
  background: #f7fbfa;
  color: var(--teal-dark);
  font-size: 13px;
  font-weight: 650;
}
.landing__eyebrow svg { width: 16px; }
.landing h1 {
  margin: 14px 0 10px;
  color: var(--ink);
  font-size: clamp(30px, 4.3vw, 60px);
  font-weight: 750;
  line-height: 1.25;
  letter-spacing: -0.04em;
}
.landing h1 span { color: var(--teal); }
.landing__intro p { margin: 0; color: var(--muted); font-size: clamp(14px, 1.3vw, 17px); }

.landing__features {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 20px;
  margin-top: clamp(24px, 4vh, 46px);
  text-align: left;
}

.feature {
  position: relative;
  min-height: 208px;
  padding: clamp(20px, 2.6vw, 34px);
  overflow: hidden;
  border: 1px solid var(--line);
  border-radius: 18px;
  background: #fff;
  box-shadow: 0 12px 26px rgba(25, 62, 70, 0.07);
}
.feature--chapters {
  border-color: #174d54;
  background: radial-gradient(ellipse at 88% 100%, #246e71, transparent 72%), #153f47;
  color: #fff;
}
.feature__content { position: relative; }
.feature__label {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  color: var(--teal-dark);
  font-size: 13px;
  font-weight: 650;
}
.feature__label svg { width: 17px; }
.feature--chapters .feature__label { color: #b5e8e0; }
.feature h2 { margin: 9px 0 6px; color: var(--ink); font-size: clamp(19px, 2vw, 26px); line-height: 1.4; }
.feature p { max-width: 32em; margin: 0; color: var(--muted); font-size: 14px; }
.feature--chapters h2 { color: inherit; }
.feature--chapters p { max-width: 22em; color: #d6e8e9; }
.feature__map {
  position: absolute;
  right: -26px;
  bottom: -52px;
  width: min(65%, 304px);
  fill: #b5e8e014;
  stroke: #b5e8e059;
  stroke-width: 1.5;
  pointer-events: none;
}
.feature__map-route { fill: none; stroke-dasharray: 4 4; }
.feature__map circle { fill: #b5e8e0; }

.feature__steps {
  display: flex;
  flex-wrap: wrap;
  gap: 6px 14px;
  margin: 16px 0 0;
  padding: 0;
  list-style: none;
  color: var(--teal-dark);
  font-size: 12px;
  font-weight: 650;
}
.feature__steps li + li::before { margin-right: 14px; color: var(--muted); content: "→"; }

.landing__enter {
  display: inline-flex;
  align-items: center;
  gap: 12px;
  min-height: 50px;
  margin-top: clamp(24px, 4vh, 42px);
  padding: 10px 24px;
  border-radius: 99px;
  background: var(--teal);
  box-shadow: 0 6px 16px rgba(0, 124, 128, 0.22);
  color: #fff;
  font-size: 16px;
  font-weight: 700;
  text-decoration: none;
}
.landing__enter:hover { background: var(--teal-dark); }
.landing__enter svg { width: 17px; }

@media (max-width: 660px) {
  .landing__features { grid-template-columns: 1fr; gap: 12px; }
  .feature { min-height: 0; }
}
</style>

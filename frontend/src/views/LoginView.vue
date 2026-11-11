<script setup lang="ts">
import { computed, nextTick, ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import { ArrowLeft, ArrowRight, Check, Hide, View } from "@element-plus/icons-vue";
import { login, register, loginDestination } from "@/api/auth";
import { toApiError } from "@/api/http";

const route = useRoute();
const router = useRouter();
const mode = ref<"login" | "register">("login");
const username = ref("");
const displayName = ref("");
const password = ref("");
const confirmation = ref("");
const visible = ref(false);
const submitting = ref(false);
const error = ref("");
const success = ref("");
const errors = ref<Record<string, string>>({});
const form = ref<HTMLFormElement>();
const registering = computed(() => mode.value === "register");
const notice = computed(() => ({ expired: "登录已过期，请重新登录后继续。", changed: "账号已在另一个页面切换，请确认当前登录账号。", unavailable: "暂时无法连接登录服务，请稍后重试。", logout: "已安全退出，你可以登录其他账号。" })[String(route.query.reason)] ?? "");

function switchMode(value: "login" | "register") {
  if (submitting.value) return;
  mode.value = value;
  password.value = "";
  confirmation.value = "";
  visible.value = false;
  error.value = "";
  success.value = "";
  errors.value = {};
}

async function submit() {
  if (submitting.value) return;
  const invalid: Record<string, string> = {};
  if (!username.value.trim()) invalid.username = "请输入用户名";
  else if (registering.value && !/^[a-zA-Z0-9_]{3,32}$/.test(username.value.trim())) invalid.username = "使用 3—32 位英文字母、数字或下划线";
  if (!password.value) invalid.password = "请输入密码";
  else if (registering.value && (password.value.length < 8 || password.value.length > 128)) invalid.password = "密码需要 8—128 个字符";
  if (registering.value) {
    if (!displayName.value.trim() || displayName.value.trim().length > 32) invalid.displayName = "显示名需要 1—32 个字符，可以使用中文";
    if (confirmation.value !== password.value) invalid.confirmation = "两次输入的密码不一致";
  }
  errors.value = invalid;
  error.value = "";
  success.value = "";
  if (Object.keys(invalid).length) {
    await nextTick();
    form.value?.querySelector<HTMLInputElement>('[aria-invalid="true"]')?.focus();
    return;
  }
  submitting.value = true;
  try {
    if (registering.value) {
      await register(username.value, password.value, displayName.value);
      mode.value = "login";
      password.value = "";
      confirmation.value = "";
      visible.value = false;
      success.value = "注册成功，请用刚刚设置的密码登录。";
      await nextTick();
      form.value?.querySelector<HTMLInputElement>('#password')?.focus();
    } else {
      await login(username.value, password.value);
      password.value = "";
      await router.replace(loginDestination(route.query.redirect));
    }
  } catch (cause) {
    const problem = toApiError(cause);
    error.value = problem.code === "LOGIN_LIMITED" ? "尝试次数过多，请稍后再试。" : problem.message;
  } finally { submitting.value = false; }
}
</script>

<template>
  <div class="auth-page">
    <header class="auth-header container">
      <RouterLink to="/" class="auth-brand" aria-label="课迹首页"><img src="/bupt-emblem.png" alt="北京邮电大学校徽" width="42" height="42" /><strong>课迹</strong><span>课程知识云台</span></RouterLink>
      <RouterLink to="/" class="auth-back"><ArrowLeft />返回首页</RouterLink>
    </header>
    <main class="auth-main container">
      <section class="auth-intro" aria-labelledby="auth-intro-title">
        <span class="auth-eyebrow"><i />让每一次回看，都有迹可循</span>
        <h1 id="auth-intro-title">回到课堂，<br />接着你的<span>思考。</span></h1>
        <p class="auth-description">把冗长录课整理成清晰线索。<br />从章节找到重点，用原文核对答案。</p>
        <div class="auth-route" aria-hidden="true">
          <div class="auth-route__line" />
          <div class="auth-route__step"><span>01</span><div><strong>上传课程</strong><small>留住老师的每一段讲解</small></div><Check /></div>
          <div class="auth-route__step"><span>02</span><div><strong>找到重点</strong><small>按章节与时间点轻松回看</small></div><Check /></div>
          <div class="auth-route__step is-current"><span>03</span><div><strong>带着问题复习</strong><small>每个回答，都能追溯原文</small></div><ArrowRight /></div>
        </div>
        <span class="auth-intro__foot">课迹 · 让课程复习回到原文与时间点</span>
      </section>

      <section class="auth-card" aria-labelledby="auth-title">
        <div class="auth-tabs" aria-label="账号操作">
          <button type="button" :class="{ 'is-active': !registering }" :aria-pressed="!registering" :disabled="submitting" @click="switchMode('login')">登录</button>
          <button type="button" :class="{ 'is-active': registering }" :aria-pressed="registering" :disabled="submitting" @click="switchMode('register')">注册</button>
        </div>
        <span class="section-kicker">{{ registering ? 'YOUR OWN SPACE' : 'WELCOME BACK' }}</span>
        <h2 id="auth-title">{{ registering ? '开启你的课程空间' : '欢迎回到课迹' }}</h2>
        <p class="auth-card__intro">{{ registering ? '创建账号，开始整理属于你的课程。' : '登录后，进入你的课程知识云台。' }}</p>
        <p v-if="success || notice" class="auth-notice" :class="{ 'is-success': success || route.query.reason === 'logout' }" role="status">{{ success || notice }}</p>
        <form ref="form" class="auth-form" novalidate :aria-busy="submitting" @submit.prevent="submit">
          <div class="auth-field">
            <label for="username">用户名</label>
            <input id="username" v-model="username" name="username" autocomplete="username" autocapitalize="none" :spellcheck="false" maxlength="32" :disabled="submitting" :aria-invalid="!!errors.username" :aria-describedby="errors.username ? 'username-error' : registering ? 'username-hint' : undefined" placeholder="请输入用户名" />
            <small v-if="errors.username" id="username-error" class="auth-field__error">{{ errors.username }}</small><small v-else-if="registering" id="username-hint">3—32 位英文字母、数字或下划线</small>
          </div>
          <div v-if="registering" class="auth-field">
            <label for="display-name">显示名</label>
            <input id="display-name" v-model="displayName" name="display-name" autocomplete="nickname" maxlength="32" :disabled="submitting" :aria-invalid="!!errors.displayName" :aria-describedby="errors.displayName ? 'display-name-error' : undefined" placeholder="希望我们怎么称呼你" />
            <small v-if="errors.displayName" id="display-name-error" class="auth-field__error">{{ errors.displayName }}</small>
          </div>
          <div class="auth-field">
            <label for="password">密码</label>
            <div class="auth-password"><input id="password" v-model="password" name="password" :type="visible ? 'text' : 'password'" :autocomplete="registering ? 'new-password' : 'current-password'" :maxlength="128" :disabled="submitting" :aria-invalid="!!errors.password" :aria-describedby="errors.password ? 'password-error' : undefined" :placeholder="registering ? '设置 8—128 位密码' : '请输入密码'" /><button type="button" :aria-label="visible ? '隐藏密码' : '显示密码'" :aria-pressed="visible" @click="visible = !visible"><Hide v-if="visible" /><View v-else /></button></div>
            <small v-if="errors.password" id="password-error" class="auth-field__error">{{ errors.password }}</small>
          </div>
          <div v-if="registering" class="auth-field">
            <label for="confirm-password">确认密码</label>
            <input id="confirm-password" v-model="confirmation" name="confirm-password" type="password" autocomplete="new-password" maxlength="128" :disabled="submitting" :aria-invalid="!!errors.confirmation" :aria-describedby="errors.confirmation ? 'confirmation-error' : undefined" placeholder="请再次输入密码" />
            <small v-if="errors.confirmation" id="confirmation-error" class="auth-field__error">{{ errors.confirmation }}</small>
          </div>
          <p v-if="error" class="auth-error" role="alert">{{ error }}</p>
          <button type="submit" class="auth-submit" :disabled="submitting"><span>{{ submitting ? (registering ? '正在创建账号…' : '正在登录…') : registering ? '创建账号' : '登录并进入云台' }}</span><ArrowRight v-if="!submitting" /></button>
        </form>
        <p class="auth-switch">{{ registering ? '已经有账号？' : '第一次使用课迹？' }}<button type="button" :disabled="submitting" @click="switchMode(registering ? 'login' : 'register')">{{ registering ? '返回登录' : '创建账号' }}</button></p>
      </section>
    </main>
  </div>
</template>

<style scoped>
.auth-page { min-height:100dvh; background:radial-gradient(ellipse at 15% 36%,#dfefeb 0,transparent 58%),linear-gradient(140deg,#f5faf8,#f8fafb); }
.auth-header { display:flex; align-items:center; justify-content:space-between; gap:16px; padding-block:24px; }
.auth-brand { display:flex; align-items:center; gap:10px; color:var(--ink); text-decoration:none; }
.auth-brand strong { font-size:24px; letter-spacing:2px; }.auth-brand > span { margin-left:8px; padding-left:16px; border-left:1px solid #cadcda; font-size:14px; color:var(--muted); }
.auth-back { display:flex; align-items:center; gap:5px; color:#5d7c7e; font-size:13px; text-decoration:none; white-space:nowrap; }.auth-back svg { width:15px; }
.auth-main { display:grid; grid-template-columns:minmax(0,1fr) minmax(350px,440px); align-items:center; gap:80px; max-width:1136px; padding-block:40px 72px; min-height:calc(100dvh - 100px); }
.auth-intro { padding:16px 0; }.auth-eyebrow { display:inline-flex; align-items:center; gap:9px; color:#397c72; font-size:13px; letter-spacing:1px; }.auth-eyebrow i { width:7px; height:7px; background:#429584; border-radius:50%; box-shadow:0 0 0 4px #d2e9e1; }
.auth-intro h1 { margin:25px 0 20px; font-size:clamp(38px,4.2vw,58px); letter-spacing:-1px; line-height:1.35; font-weight:750; color:#173b3c; }.auth-intro h1 span { color:var(--teal); }
.auth-description { color:#66807f; font-size:15px; line-height:1.9; }
.auth-route { position:relative; display:grid; gap:24px; max-width:360px; margin:38px 0; }.auth-route__line { position:absolute; left:19px; top:24px; bottom:24px; border-left:1px dashed #99c5b9; }
.auth-route__step { position:relative; display:flex; align-items:center; gap:16px; }.auth-route__step > span { display:grid; place-items:center; width:39px; height:39px; flex-shrink:0; border:1px solid #b6d4ca; border-radius:50%; background:#f0f8f4; color:#4e8a7b; font:12px Consolas,monospace; }.auth-route__step div { display:flex; flex-direction:column; gap:5px; }.auth-route__step strong { font-size:14px; font-weight:600; }.auth-route__step small { color:#7f9692; font-size:12px; }.auth-route__step svg { margin-left:auto; width:16px; color:#8bb5a8; }.auth-route__step.is-current > span { background:#0f7d80; color:#fff; border-color:#0f7d80; box-shadow:0 0 0 5px #dbeee7; }.auth-route__step.is-current svg { color:#0f7d80; }
.auth-intro__foot { color:#8ca19b; font-size:11px; letter-spacing:1px; }
.auth-card { padding:32px 36px 25px; border:1px solid #e1ebe7; border-radius:22px; background:#fff; box-shadow:0 18px 64px #214d3d0d,0 2px 8px #214d3d04; }
.auth-tabs { display:flex; gap:4px; padding:4px; margin-bottom:30px; border-radius:10px; background:#f0f5f3; }.auth-tabs button { flex:1; border:0; border-radius:7px; padding:9px; background:transparent; color:#7c928a; font-size:14px; cursor:pointer; }.auth-tabs button.is-active { background:#fff; color:#0a7776; font-weight:700; box-shadow:0 2px 7px #2043360a; }
.auth-card .section-kicker { margin-bottom:9px; font-size:10px; letter-spacing:2px; }.auth-card h2 { margin:0; color:#1f3d39; font-size:26px; line-height:1.4; letter-spacing:.3px; }.auth-card__intro { margin:10px 0 26px; color:#80928d; font-size:13px; }
.auth-form { display:grid; gap:18px; }.auth-field { display:grid; gap:8px; }.auth-field label { font-size:13px; color:#48645b; }.auth-field input { width:100%; min-width:0; height:46px; padding:0 13px; border:1px solid #dce6e1; border-radius:9px; background:#fbfdfc; color:#23483c; font:14px inherit; font-family:inherit; font-size:14px; transition:border-color .15s,box-shadow .15s; }.auth-field input::placeholder { color:#acb9b2; }.auth-field input:focus { outline:0; border-color:#459d8d; box-shadow:0 0 0 3px #e2f3ed; background:#fff; }.auth-field input[aria-invalid="true"] { border-color:#c96c59; }.auth-field small { font-size:11px; color:#90a19b; }.auth-field small.auth-field__error { color:#b54f3d; }
.auth-password { position:relative; }.auth-password input { padding-right:46px; }.auth-password button { display:grid; place-items:center; position:absolute; inset:5px 5px 5px auto; width:36px; padding:8px; border:0; border-radius:6px; background:transparent; color:#8da399; cursor:pointer; }.auth-password button:hover { background:#eef5f1; color:#0f7d80; }
.auth-submit { display:flex; align-items:center; justify-content:center; gap:16px; min-height:48px; margin-top:7px; padding:12px; border:1px solid #0b7576; border-radius:9px; background:linear-gradient(110deg,#108884,#087273); box-shadow:0 5px 12px #0872731a; color:#fff; font-size:14px; font-weight:600; cursor:pointer; }.auth-submit svg { width:16px; }.auth-submit:hover { background:#087273; }.auth-submit:disabled { opacity:.65; cursor:wait; }
.auth-notice,.auth-error { padding:10px 12px; border-radius:7px; font-size:12px; line-height:1.7; overflow-wrap:anywhere; }.auth-notice { margin:-8px 0 20px; background:#fff7e9; color:#966a27; }.auth-notice.is-success { background:#edf8f2; color:#287e5a; }.auth-error { margin:0; background:#fff2ee; color:#b3543d; }
.auth-switch { display:flex; justify-content:center; align-items:center; gap:4px; margin:23px 0; color:#91a098; font-size:12px; }.auth-switch button { padding:3px; border:0; background:transparent; color:#0d7e74; font:inherit; cursor:pointer; }
.auth-privacy { display:flex; align-items:flex-start; justify-content:center; gap:7px; margin:0; padding-top:19px; border-top:1px solid #f0f4f1; color:#9aa9a1; font-size:10px; line-height:1.8; }.auth-privacy span { flex-shrink:0; width:6px; height:6px; margin-top:5px; border-radius:50%; background:#8fb8a5; }
@media(max-width:1050px) { .auth-main { gap:42px; }.auth-intro h1 { font-size:46px; } }
@media(max-width:760px) { .auth-header { padding-block:18px; }.auth-brand > span { display:none; }.auth-brand img { width:36px; height:36px; }.auth-brand strong { font-size:21px; }.auth-main { grid-template-columns:minmax(0,440px); justify-content:center; gap:24px; padding-block:18px 80px; min-height:0; }.auth-intro { display:none; }.auth-card { padding:28px 26px 24px; border-radius:18px; }.auth-card h2 { font-size:25px; } }
@media(prefers-reduced-motion:reduce) { .auth-field input { transition:none; } }
</style>

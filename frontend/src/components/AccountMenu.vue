<script setup lang="ts">
import { ref } from "vue";
import { ArrowDown, SwitchButton } from "@element-plus/icons-vue";
import { ElMessage } from "element-plus";
import { useRouter } from "vue-router";
import { logout } from "@/api/auth";
import { isMock, toApiError } from "@/api/http";
import { sessionState } from "@/stores/session";
const { user } = sessionState;
const router = useRouter();
const busy = ref(false);
async function signOut() {
  if (busy.value) return;
  busy.value = true;
  try { await logout(); await router.replace({ name: "login", query: { reason: "logout" } }); }
  catch (error) { if (user.value) ElMessage.error(toApiError(error).message); }
  finally { busy.value = false; }
}
</script>

<template>
  <span v-if="isMock" class="account-demo">开发预览</span>
  <el-dropdown v-else-if="user" trigger="click" placement="bottom-end" @command="signOut">
    <button class="account-trigger" type="button" :disabled="busy" aria-label="账号菜单">
      <span class="account-avatar" aria-hidden="true">{{ user.display_name.slice(0, 1) }}</span>
      <span class="account-name">{{ user.display_name }}</span><ArrowDown />
    </button>
    <template #dropdown>
      <el-dropdown-menu class="account-menu">
        <li class="account-info"><strong>{{ user.display_name }}</strong><small>@{{ user.username }}</small></li>
        <el-dropdown-item command="logout" :disabled="busy" :icon="SwitchButton" divided>{{ busy ? '正在退出…' : '退出登录' }}</el-dropdown-item>
      </el-dropdown-menu>
    </template>
  </el-dropdown>
  <RouterLink v-else to="/login" class="account-login">登录 / 注册</RouterLink>
</template>

<style scoped>
.account-trigger { display:flex; align-items:center; gap:8px; max-width:180px; padding:4px 7px 4px 4px; border:1px solid #d9e8e5; border-radius:30px; background:#fff; color:var(--ink); font:inherit; font-size:13px; cursor:pointer; }
.account-trigger:hover { border-color:var(--teal); background:#f5fbf9; }
.account-avatar { display:grid; place-items:center; width:28px; height:28px; flex-shrink:0; border-radius:50%; background:#e6f3f0; color:#096b6d; font-size:13px; font-weight:700; }
.account-name { max-width:96px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.account-trigger svg { width:12px; flex-shrink:0; }
.account-info { display:flex; flex-direction:column; gap:4px; padding:10px 18px; max-width:240px; overflow-wrap:anywhere; list-style:none; color:var(--ink); }
.account-info small { color:var(--muted); }
.account-login { display:inline-flex; align-items:center; padding:8px 16px; border-radius:24px; background:var(--teal); color:#fff; font-size:14px; white-space:nowrap; text-decoration:none; }
.account-demo { color:var(--muted); font-size:12px; }
@media(max-width:700px) { .account-name { max-width:65px; }.account-trigger { gap:5px; }.account-login { padding:7px 12px; } }
</style>

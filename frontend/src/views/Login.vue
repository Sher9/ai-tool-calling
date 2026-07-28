<template>
  <div class="login-wrap">
    <el-card class="login-card" shadow="never">
      <div class="brand">
        <span class="brand-logo"><ChatDotRound /></span>
        <div class="brand-text">
          <div class="brand-name">AI Agent 平台</div>
          <div class="brand-tag">智能工具调度 · 企业助手</div>
        </div>
      </div>
      <h2 class="title">欢迎登录</h2>
      <p class="sub">私有化部署 · 自然语言调度内部工具</p>
      <el-form @submit.prevent="doLogin">
        <el-form-item>
          <el-input v-model="username" placeholder="用户名" size="large" :prefix-icon="User" />
        </el-form-item>
        <el-form-item>
          <el-input v-model="password" type="password" placeholder="密码" size="large" :prefix-icon="Lock" show-password @keyup.enter="doLogin" />
        </el-form-item>
        <el-button type="primary" size="large" class="login-btn" style="width:100%" :loading="loading" @click="doLogin">登录</el-button>
      </el-form>
      <el-alert v-if="error" :title="error" type="error" show-icon class="mt" :closable="false" />
      <div class="hint">演示账号：<b>admin/admin123</b>（管理员）· <b>alice/alice123</b>（销售）· <b>carol/carol123</b>（研发）· <b>dave/dave123</b>（财务）· <b>erin/erin123</b>（人事）</div>
    </el-card>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { api } from '../api.js'
import { ElMessage } from 'element-plus'
import { User, Lock, ChatDotRound } from '@element-plus/icons-vue'

const emit = defineEmits(['logged'])
const username = ref('')
const password = ref('')
const loading = ref(false)
const error = ref('')

async function doLogin() {
  error.value = ''
  loading.value = true
  try {
    const { data } = await api.login(username.value, password.value)
    localStorage.setItem('token', data.access_token)
    const me = await api.me()
    localStorage.setItem('user', JSON.stringify(me.data))
    emit('logged', me.data)
  } catch (e) {
    error.value = e.response?.data?.detail || '登录失败'
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-wrap {
  position: relative;
  min-height: 100vh;
  display: flex; align-items: center; justify-content: center;
  padding: var(--space-6);
  overflow: hidden;
  /* 极简风柔光背景：浅蓝底 + 蓝色/青色双光晕 + 细微点阵，避免纯色空洞与 AI 紫光 */
  background:
    radial-gradient(120% 120% at 12% 16%, rgba(37, 99, 235, 0.10), transparent 55%),
    radial-gradient(120% 120% at 88% 84%, rgba(8, 145, 178, 0.10), transparent 55%),
    radial-gradient(circle at 1px 1px, rgba(37, 99, 235, 0.07) 1px, transparent 0) 0 0 / 22px 22px,
    linear-gradient(135deg, #f9f9fb 0%, #eef3fc 100%);
}
/* 缓慢漂浮的大光斑，制造层次与呼吸感（克制动效） */
.login-wrap::before,
.login-wrap::after {
  content: '';
  position: absolute;
  border-radius: 50%;
  filter: blur(64px);
  z-index: 0;
  pointer-events: none;
}
.login-wrap::before {
  width: 46vmax; height: 46vmax;
  top: -14vmax; left: -10vmax;
  background: radial-gradient(circle, rgba(37, 99, 235, 0.26), transparent 70%);
  animation: float1 18s ease-in-out infinite;
}
.login-wrap::after {
  width: 40vmax; height: 40vmax;
  bottom: -12vmax; right: -8vmax;
  background: radial-gradient(circle, rgba(8, 145, 178, 0.22), transparent 70%);
  animation: float2 22s ease-in-out infinite;
}

.login-card {
  position: relative;
  z-index: 1;
  width: 404px; max-width: 100%;
  border-radius: var(--radius-2xl);
  /* 毛玻璃卡片，悬浮于柔光背景之上 */
  background: rgba(255, 255, 255, 0.72);
  backdrop-filter: blur(22px) saturate(150%);
  -webkit-backdrop-filter: blur(22px) saturate(150%);
  border: 1px solid rgba(255, 255, 255, 0.65);
  box-shadow: var(--shadow-xl);
  overflow: hidden;
  animation: rise 0.6s var(--motion-easing-decelerate) both;
}
.login-card :deep(.el-card__body) { padding: var(--space-10); }
.brand { display: flex; align-items: center; gap: var(--space-3); margin-bottom: var(--space-6); }
.brand-logo {
  display: inline-flex; align-items: center; justify-content: center;
  width: 44px; height: 44px; border-radius: var(--radius-lg);
  background: linear-gradient(135deg, var(--color-primary), var(--el-color-primary-dark-2));
  color: #fff; box-shadow: var(--shadow-md);
}
.brand-logo :deep(svg) { width: 24px; height: 24px; }
.brand-text { display: flex; flex-direction: column; }
.brand-name { font-size: var(--font-size-lg); font-weight: var(--font-weight-semibold); color: var(--color-text); letter-spacing: var(--font-letterSpacing-tighter); }
.brand-tag { font-size: var(--font-size-xs); color: var(--color-text-3); margin-top: var(--space-1); }
.title { margin: 0; font-size: var(--font-size-2xl); font-weight: var(--font-weight-semibold); letter-spacing: var(--font-letterSpacing-tighter); color: var(--color-text); }
.sub { color: var(--color-text-3); margin: var(--space-2) 0 var(--space-6); font-size: var(--font-size-sm); }

/* 输入框聚焦高亮，与聊天页 composer 一致 */
.login-wrap :deep(.el-input__wrapper) {
  border-radius: var(--radius-lg);
  background: rgba(255, 255, 255, 0.7);
  box-shadow: 0 0 0 1px var(--color-border) inset;
  transition: box-shadow var(--motion-duration-fast) var(--motion-easing-standard);
}
.login-wrap :deep(.el-input__wrapper.is-focus) {
  box-shadow: 0 0 0 1px var(--color-primary) inset,
              0 0 0 4px color-mix(in srgb, var(--color-primary) 14%, transparent);
}

.login-btn.el-button--primary {
  margin-top: var(--space-1);
  height: 44px;
  font-weight: var(--font-weight-medium);
  background: linear-gradient(135deg, var(--color-primary), var(--el-color-primary-dark-2));
  border-color: transparent;
  box-shadow: var(--shadow-md);
  transition: filter var(--motion-duration-fast) var(--motion-easing-standard),
              box-shadow var(--motion-duration-fast) var(--motion-easing-standard);
}
.login-btn.el-button--primary:hover {
  filter: brightness(1.05);
  box-shadow: var(--shadow-lg);
}
.mt { margin-top: var(--space-4); }
.hint {
  margin-top: var(--space-5); font-size: var(--font-size-xs); color: var(--color-text-3);
  line-height: 1.7; padding-top: var(--space-4); border-top: 1px solid var(--color-border);
}
.hint b { color: var(--color-text-2); font-weight: var(--font-weight-medium); }

@keyframes rise {
  from { opacity: 0; transform: translateY(14px); }
  to   { opacity: 1; transform: none; }
}
@keyframes float1 {
  0%, 100% { transform: translate(0, 0) scale(1); }
  50%      { transform: translate(4vmax, 3vmax) scale(1.08); }
}
@keyframes float2 {
  0%, 100% { transform: translate(0, 0) scale(1); }
  50%      { transform: translate(-3vmax, -4vmax) scale(1.06); }
}
@media (prefers-reduced-motion: reduce) {
  .login-wrap::before, .login-wrap::after, .login-card { animation: none; }
}
</style>

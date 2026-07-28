<template>
  <Login v-if="!user" @logged="onLogged" />
  <el-container v-else class="layout">
    <el-aside width="240px" class="aside">
      <div class="brand">
        <span class="brand-logo"><ChatDotRound /></span>
        <div class="brand-text">
          <span class="brand-name">AI Agent 平台</span>
          <span class="brand-tag">智能工具调度</span>
        </div>
      </div>
      <el-button type="primary" class="newchat" @click="newChat"><el-icon><Plus /></el-icon><span>新对话</span></el-button>
      <div class="conv-list">
        <div v-for="c in conversations" :key="c.id" class="conv"
             :class="{ active: c.id === activeConv }" @click="selectConv(c.id)">
          <span class="conv-title">{{ c.title }}</span>
          <el-icon class="del" @click.stop="delConv(c.id)"><Delete /></el-icon>
        </div>
        <el-empty v-if="!conversations.length" description="暂无对话" :image-size="50" />
      </div>
    </el-aside>

    <el-container>
      <el-header class="topbar">
        <span class="who"><span class="avatar">{{ user.display_name.slice(0, 1) }}</span>{{ user.display_name }}（{{ roleLabel }}）</span>
        <span class="spacer" />
        <el-button size="small" @click="knowledgeVisible = true">知识库</el-button>
        <el-button v-if="user.role === 'admin'" size="small" type="warning" @click="adminVisible = true">管理员后台</el-button>
        <el-button size="small" @click="logout">退出</el-button>
      </el-header>
      <Chat :conversationId="activeConv" :key="activeConv || 'new'" @created="onCreated" @updated="loadConversations" />
    </el-container>

    <el-drawer v-model="adminVisible" title="管理员后台" size="70%">
      <Admin @close="adminVisible = false" />
    </el-drawer>

    <el-drawer v-model="knowledgeVisible" title="知识库管理" size="56%" :destroy-on-close="true">
      <Knowledge :department="user.department" />
    </el-drawer>
  </el-container>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import Login from './views/Login.vue'
import Chat from './views/Chat.vue'
import Admin from './views/Admin.vue'
import Knowledge from './views/Knowledge.vue'
import { api } from './api.js'
import { Delete, ChatDotRound, Plus } from '@element-plus/icons-vue'

const user = ref(null)
const conversations = ref([])
const activeConv = ref(null)
const adminVisible = ref(false)
const knowledgeVisible = ref(false)

const roleLabel = computed(() => ({ admin: '管理员', sales: '销售', tech: '研发', finance: '财务', hr: '人事', employee: '员工' }[user.value?.role] || '员工'))

function onLogged(u) {
  user.value = u
  loadConversations()
}
function logout() {
  localStorage.removeItem('token'); localStorage.removeItem('user'); user.value = null
}
async function loadConversations() {
  try { conversations.value = (await api.listConversations()).data } catch (e) {}
}
function newChat() { activeConv.value = null }
function selectConv(id) { activeConv.value = id }
async function delConv(id) {
  await api.deleteConversation(id)
  if (activeConv.value === id) activeConv.value = null
  loadConversations()
}
function onCreated(id) { activeConv.value = id; loadConversations() }

onMounted(() => {
  const u = localStorage.getItem('user')
  if (u) { user.value = JSON.parse(u); loadConversations() }
})
</script>

<style scoped>
.layout { height: 100vh; background: var(--color-bg); }
.aside {
  background: var(--color-surface);
  border-right: 1px solid var(--color-border);
  display: flex; flex-direction: column; padding: var(--space-4) var(--space-3);
}
.brand { display: flex; align-items: center; gap: var(--space-3); padding: var(--space-2) var(--space-2) var(--space-4); }
.brand-text { display: flex; flex-direction: column; }
.brand-name { font-size: var(--font-size-base); font-weight: var(--font-weight-semibold); color: var(--color-text); letter-spacing: var(--font-letterSpacing-tighter); }
.brand-tag { font-size: var(--font-size-xs); color: var(--color-text-3); margin-top: var(--space-1); }
.newchat { width: 100%; margin-bottom: var(--space-4); justify-content: center; }
.conv-list { flex: 1; overflow-y: auto; display: flex; flex-direction: column; gap: var(--space-1); padding-right: var(--space-1); }
.conv {
  position: relative;
  padding: var(--space-2) var(--space-3); border-radius: var(--radius-md); cursor: pointer;
  display: flex; justify-content: space-between; align-items: center;
  color: var(--color-text-2);
  transition: background var(--motion-duration-fast) var(--motion-easing-standard),
              color var(--motion-duration-fast) var(--motion-easing-standard);
}
.conv::before {
  content: ''; position: absolute; left: 0; top: 50%; transform: translateY(-50%);
  width: 3px; height: 0; border-radius: var(--radius-full); background: var(--color-primary);
  transition: height var(--motion-duration-fast) var(--motion-easing-standard);
}
.conv:hover { background: var(--color-surface-2); color: var(--color-text); }
.conv.active { background: var(--el-color-primary-light-9); color: var(--color-primary); font-weight: 500; }
.conv.active::before { height: 60%; }
.conv-title { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: var(--font-size-sm); }
.del { opacity: 0; color: var(--color-text-3); transition: opacity var(--motion-duration-fast); }
.conv:hover .del { opacity: .65; }
.del:hover { color: var(--color-danger); opacity: 1; }
.topbar {
  display: flex; align-items: center; gap: var(--space-2);
  background: var(--color-surface);
  border-bottom: 1px solid var(--color-border);
  padding: 0 var(--space-5); height: 56px;
  box-shadow: var(--shadow-sm);
}
.who { display: flex; align-items: center; gap: var(--space-2); font-weight: var(--font-weight-semibold); color: var(--color-text); font-size: var(--font-size-sm); }
.avatar {
  display: inline-flex; align-items: center; justify-content: center;
  width: 28px; height: 28px; border-radius: var(--radius-full);
  background: var(--el-color-primary-light-9); color: var(--color-primary);
  font-size: var(--font-size-xs); font-weight: var(--font-weight-semibold);
}
.spacer { flex: 1; }
</style>

<template>
  <div class="admin">
    <el-row :gutter="12" class="stats">
      <el-col :span="4" v-for="(v, k) in visibleStats" :key="k" style="margin-top: 5px;">
        <el-card shadow="hover" class="stat-card">
          <span class="stat-ico" :class="'ico-' + k"><el-icon><component :is="iconOf(k)" /></el-icon></span>
          <div class="stat-body">
            <div class="stat-label">{{ labelOf(k) }}</div>
            <div class="num">{{ v }}</div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <el-tabs v-model="tab">
      <el-tab-pane label="工具管理" name="tools">
        <el-table :data="tools" size="small" border>
          <el-table-column prop="display_name" label="名称" />
          <el-table-column prop="category" label="分类" width="100" />
          <el-table-column prop="allowed_roles" label="可访问角色" />
          <el-table-column label="状态" width="100">
            <template #default="{ row }"><el-tag :type="row.enabled ? 'success' : 'info'">{{ row.enabled ? '启用' : '停用' }}</el-tag></template>
          </el-table-column>
          <el-table-column label="操作" width="100">
            <template #default="{ row }">
              <el-button size="small" @click="toggleTool(row)">{{ row.enabled ? '停用' : '启用' }}</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <el-tab-pane label="操作审计" name="audit">
        <el-alert v-if="alerts.length" type="warning" :closable="false" :title="`敏感操作告警 ${alerts.length} 条`" class="mb" />
        <el-table :data="audit" size="small" border height="420">
          <el-table-column prop="username" label="用户" width="100" />
          <el-table-column prop="action" label="动作" width="110" />
          <el-table-column prop="resource" label="资源" width="140" />
          <el-table-column prop="ip" label="IP" width="120" />
          <el-table-column label="敏感" width="70">
            <template #default="{ row }"><el-tag v-if="row.sensitive" type="danger">敏感</el-tag></template>
          </el-table-column>
          <el-table-column prop="created_at" label="时间" />
        </el-table>
      </el-tab-pane>

      <el-tab-pane label="用户管理" name="users">
        <el-button size="small" type="primary" class="mb" @click="showUser = true">新增用户</el-button>
        <el-table :data="users" size="small" border>
          <el-table-column prop="username" label="用户名" />
          <el-table-column prop="display_name" label="姓名" />
          <el-table-column prop="role" label="角色" />
          <el-table-column prop="department" label="部门" />
        </el-table>
      </el-tab-pane>

      <el-tab-pane label="提示词" name="prompts">
        <div v-for="p in prompts" :key="p.key" class="prompt">
          <h4>{{ p.title }} <small>({{ p.key }})</small></h4>
          <el-input type="textarea" :rows="3" v-model="p.content" />
          <el-button size="small" class="mb" @click="savePrompt(p)">保存</el-button>
        </div>
      </el-tab-pane>

      <el-tab-pane label="系统设置" name="settings">
        <el-form label-width="160px">
          <el-form-item label="外网检索工具">
            <el-switch v-model="externalOn" @change="setExternal" />
            <span class="tip">默认关闭，开启后员工可使用天气/日历/域名等外网工具</span>
          </el-form-item>
          <el-form-item label="大模型模式">
            <el-tag>{{ settings.mock_llm ? 'Mock 规划（无需真实模型）' : '真实模型' }}</el-tag>
          </el-form-item>
        </el-form>
      </el-tab-pane>
    </el-tabs>

    <el-dialog v-model="showUser" title="新增用户">
      <el-form :model="newUser">
        <el-form-item label="用户名"><el-input v-model="newUser.username" /></el-form-item>
        <el-form-item label="姓名"><el-input v-model="newUser.display_name" /></el-form-item>
        <el-form-item label="密码"><el-input v-model="newUser.password" /></el-form-item>
        <el-form-item label="角色">
          <el-select v-model="newUser.role">
            <el-option v-for="r in ['employee','sales','tech','finance','hr','admin']" :key="r" :label="r" :value="r" />
          </el-select>
        </el-form-item>
        <el-form-item label="部门"><el-input v-model="newUser.department" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showUser = false">取消</el-button>
        <el-button type="primary" @click="createUser">创建</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { api } from '../api.js'
import { ElMessage } from 'element-plus'

const emit = defineEmits(['close'])
const tab = ref('tools')
const stats = ref({})
const tools = ref([])
const audit = ref([])
const alerts = ref([])
const users = ref([])
const prompts = ref([])
const settings = ref({ mock_llm: true, external_tools_enabled: false })
const externalOn = ref(false)
const showUser = ref(false)
const newUser = ref({ username: '', display_name: '', password: '', role: 'employee', department: 'general' })

const LABELS = { users: '用户数', tools: '工具数', tools_enabled: '启用工具', conversations: '对话数', tasks: '任务数', audit: '审计数', sensitive_alerts: '敏感告警' }
const labelOf = (k) => LABELS[k] || k
const ICONS = { users: 'User', tools: 'Tools', tools_enabled: 'Operation', conversations: 'ChatDotRound', tasks: 'List', audit: 'Document', sensitive_alerts: 'WarningFilled' }
const iconOf = (k) => ICONS[k] || 'Info'
// 统计卡片隐藏“启用工具”项
const hiddenStats = new Set(['tools_enabled'])
const visibleStats = computed(() => Object.fromEntries(Object.entries(stats.value).filter(([k]) => !hiddenStats.has(k))))

async function loadAll() {
  try {
    stats.value = (await api.admin.stats()).data
    tools.value = (await api.listTools()).data
    audit.value = (await api.admin.audit({ limit: 200 })).data
    alerts.value = (await api.admin.alerts()).data
    users.value = (await api.admin.users()).data
    prompts.value = (await api.admin.prompts()).data
    settings.value = (await api.admin.settings()).data
    externalOn.value = settings.value.external_tools_enabled
  } catch (e) { /* permission */ }
}

function toggleTool(row) {
  doToggle(row)
}
async function doToggle(row) {
  await fetch(`/api/v1/tools/${row.id}/toggle`, { method: 'POST', headers: { Authorization: `Bearer ${localStorage.getItem('token')}` } })
  row.enabled = !row.enabled
}

async function savePrompt(p) {
  await api.admin.updatePrompt(p.key, { content: p.content, title: p.title })
  ElMessage.success('已保存')
}
async function createUser() {
  await api.admin.createUser(newUser.value)
  showUser.value = false
  await loadAll()
}
async function setExternal(v) {
  await api.admin.setExternal(v)
  ElMessage.success('外网工具已' + (v ? '开启' : '关闭'))
}

onMounted(loadAll)
</script>

<style scoped>
.admin { padding: var(--space-1); }
.stats { margin-bottom: var(--space-5); }
.stat-card :deep(.el-card__body) { display: flex; align-items: center; gap: var(--space-3); width: 100%; }
.stat-ico {
  flex: none; display: inline-flex; align-items: center; justify-content: center;
  width: 40px; height: 40px; border-radius: var(--radius-md);
  background: var(--el-color-primary-light-9); color: var(--color-primary);
}
.stat-ico :deep(.el-icon), .stat-ico svg { width: 22px; height: 22px; }
.ico-sensitive_alerts { background: color-mix(in srgb, var(--color-danger) 12%, #fff); color: var(--color-danger); }
.stat-body { display: flex; flex-direction: column; min-width: 0; }
.stat-label { font-size: var(--font-size-xs); color: var(--color-text-3); }
.num { font-size: var(--font-size-3xl); font-weight: var(--font-weight-semibold); color: var(--color-text); letter-spacing: var(--font-letterSpacing-tighter); line-height: 1.1; }
.mb { margin-bottom: var(--space-3); }
.tip { color: var(--color-text-3); margin-left: var(--space-3); font-size: var(--font-size-xs); }
.prompt { margin-bottom: var(--space-4); }
.prompt h4 { margin: var(--space-2) 0; font-weight: var(--font-weight-semibold); color: var(--color-text); }
.prompt h4 small { color: var(--color-text-3); font-weight: 400; font-family: var(--font-mono); }
.admin :deep(.el-card) { border: 1px solid var(--color-border); border-radius: var(--radius-lg); }
</style>

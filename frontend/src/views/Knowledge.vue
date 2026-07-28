<template>
  <div class="kb">
    <el-card shadow="never" class="panel">
      <template #header>
        <div class="hd">
          <span class="title"><el-icon><Files /></el-icon>上传知识库文档</span>
          <el-tag size="small" type="info">解析 → 智能分块 → 向量化入库</el-tag>
        </div>
      </template>

      <el-upload
        ref="uploadRef"
        drag
        :auto-upload="false"
        :limit="1"
        :show-file-list="true"
        :on-change="onFile"
        accept=".pdf,.docx,.xlsx,.txt,.md"
      >
        <el-icon class="el-icon--upload"><UploadFilled /></el-icon>
        <div class="up-tip">将文件拖到此处，或点击选择（PDF / Word / Excel / TXT / Markdown）</div>
      </el-upload>

      <el-form :model="form" label-width="92px" class="meta">
        <el-row :gutter="12">
          <el-col :span="8">
            <el-form-item label="文档类型">
              <el-select v-model="form.doc_type" placeholder="选择类型">
                <el-option v-for="t in docTypes" :key="t" :label="t" :value="t" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="密级">
              <el-select v-model="form.trust_level" placeholder="选择密级">
                <el-option v-for="t in trustLevels" :key="t" :label="t" :value="t" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="来源">
              <el-input v-model="form.source" placeholder="可选，如：法务部制度库" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="标签">
          <el-select v-model="form.tags" multiple filterable allow-create default-first-option
                     placeholder="可输入并回车创建标签" style="width: 100%">
            <el-option v-for="t in form.tags" :key="t" :label="t" :value="t" />
          </el-select>
        </el-form-item>
      </el-form>

      <div class="actions">
        <el-button type="primary" :loading="uploading" :disabled="!pendingFile" @click="doUpload">
          上传并向量化
        </el-button>
        <el-button @click="resetForm">清空</el-button>
      </div>
    </el-card>

    <el-card shadow="never" class="panel">
      <template #header>
        <div class="hd">
          <span class="title"><el-icon><Collection /></el-icon>已入库文档（{{ docs.length }}）</span>
          <el-button size="small" :icon="Refresh" @click="loadDocs">刷新</el-button>
        </div>
      </template>

      <el-table :data="docs" stripe style="width: 100%" empty-text="暂无文档">
        <el-table-column prop="title" label="文件名" min-width="160" show-overflow-tooltip />
        <el-table-column prop="doc_type" label="类型" width="100" />
        <el-table-column prop="department" label="部门" width="100" />
        <el-table-column prop="trust_level" label="密级" width="100">
          <template #default="{ row }">
            <el-tag size="small" :type="trustTag(row.trust_level)">{{ row.trust_level }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="分块数" width="100">
          <template #default="{ row }">{{ row.chunk_count }}</template>
        </el-table-column>
        <el-table-column prop="doc_status" label="状态" width="90">
          <template #default="{ row }">
            <el-tag size="small" :type="row.doc_status === 'active' ? 'success' : 'warning'">
              {{ row.doc_status }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="入库时间" width="170" />
        <el-table-column label="操作" width="90" fixed="right">
          <template #default="{ row }">
            <el-button size="small" type="danger" link @click="delDoc(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { UploadFilled, Refresh, Files, Collection } from '@element-plus/icons-vue'
import { api } from '../api.js'

const props = defineProps({ department: { type: String, default: '' } })

const uploadRef = ref(null)
const pendingFile = ref(null)
const uploading = ref(false)
const docs = ref([])

const docTypes = ['faq', 'manual', 'regulation', 'book', 'general']
const trustLevels = ['public', 'internal', 'confidential']

const form = reactive({
  doc_type: 'general',
  trust_level: 'internal',
  source: '',
  tags: []
})

function onFile(file) {
  const ok = /\.(pdf|docx|xlsx|txt|md)$/i.test(file.name)
  if (!ok) { ElMessage.error('仅支持 PDF / Word / Excel / TXT / Markdown'); return }
  pendingFile.value = file.raw
}
function resetForm() {
  pendingFile.value = null
  uploadRef.value?.clearFiles()
  form.doc_type = 'general'
  form.trust_level = 'internal'
  form.source = ''
  form.tags = []
}
async function doUpload() {
  if (!pendingFile.value) return
  uploading.value = true
  try {
    const res = await api.uploadKnowledge(pendingFile.value, {
      department: props.department,
      doc_type: form.doc_type,
      trust_level: form.trust_level,
      source: form.source,
      tags: form.tags
    })
    const d = res.data
    ElMessage.success(`已入库：${d.title}（${d.chunk_count} 个分块）`)
    resetForm()
    loadDocs()
  } catch (e) {
    ElMessage.error('上传失败：' + (e.response?.data?.detail || e.message))
  } finally {
    uploading.value = false
  }
}

async function loadDocs() {
  try { docs.value = (await api.listDocs()).data } catch (e) {}
}
async function delDoc(row) {
  try {
    await ElMessageBox.confirm(`确认删除《${row.title}》及其所有分块？`, '删除确认', { type: 'warning' })
  } catch { return }
  try {
    await api.deleteDoc(row.id)
    ElMessage.success('已删除')
    loadDocs()
  } catch (e) { ElMessage.error('删除失败') }
}

function trustTag(level) {
  return { public: 'success', internal: 'info', confidential: 'danger' }[level] || 'info'
}

onMounted(loadDocs)
</script>

<style scoped>
.kb { display: flex; flex-direction: column; gap: var(--space-4); }
.kb .panel { border: 1px solid var(--color-border); border-radius: var(--radius-lg); box-shadow: var(--shadow-sm); overflow: hidden; }
.kb :deep(.el-card__header) { border-bottom: 1px solid var(--color-border); padding: var(--space-3) var(--space-5); }
.kb :deep(.el-card__body) { padding: var(--space-5); }
.hd { display: flex; align-items: center; justify-content: space-between; gap: var(--space-2); }
.title { display: inline-flex; align-items: center; gap: var(--space-2); font-weight: var(--font-weight-semibold); color: var(--color-text); font-size: var(--font-size-base); }
.up-tip { color: var(--color-text-3); font-size: var(--font-size-sm); }
.kb :deep(.el-upload-dragger) {
  background: var(--color-surface-2); border: 1px dashed var(--color-border);
  border-radius: var(--radius-lg); padding: var(--space-8) 0;
  transition: all var(--motion-duration-fast) var(--motion-easing-standard);
}
.kb :deep(.el-upload-dragger:hover) { border-color: var(--color-primary); background: var(--el-color-primary-light-9); }
.kb :deep(.el-upload-dragger .el-icon--upload) { color: var(--color-primary); transition: transform var(--motion-duration-fast) var(--motion-easing-standard); }
.kb :deep(.el-upload-dragger .el-icon--upload svg) { width: 46px; height: 46px; }
.kb :deep(.el-upload-dragger:hover .el-icon--upload) { transform: translateY(-2px); }
.meta { margin-top: var(--space-4); }
.actions { margin-top: var(--space-2); text-align: right; }
.kb :deep(.el-table) { --el-table-border-color: var(--color-border); border-radius: var(--radius-md); overflow: hidden; }
.kb :deep(.el-table th.el-table__cell) { background: var(--color-surface-2); font-weight: var(--font-weight-semibold); color: var(--color-text-2); }
</style>

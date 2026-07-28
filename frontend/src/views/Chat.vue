<template>
  <div class="chat">
    <div class="thread" ref="box">
      <div v-if="!messages.length" class="welcome">
        <div class="welcome-badge"><ChatRound /></div>
        <h1 class="welcome-title">你好，我是你的智能办公助手</h1>
        <p class="welcome-sub">用自然语言描述任务，我会自动调度合适的工具并检索知识库来帮你完成。</p>
        <div class="welcome-grid">
          <button v-for="ex in examples" :key="ex" class="suggest" @click="sendExample(ex)">
            <span class="suggest-ico"><Promotion /></span>
            <span class="suggest-text">{{ ex }}</span>
          </button>
        </div>
      </div>

      <div v-for="(m, i) in messages" :key="i" class="msg" :class="m.role">
        <span class="avatar" :class="m.role">
          <ChatDotRound v-if="m.role === 'assistant'" />
          <User v-else />
        </span>
        <div class="bubble">
          <pre v-if="m.role === 'user'">{{ m.content }}</pre>
          <div v-else>
            <pre>{{ m.content }}</pre>

            <!-- 图表（mermaid 流程图 / 自动生成图片）在回答中可视化展示 -->
            <div v-if="m.charts && m.charts.length" class="charts">
              <div v-for="(c, ci) in m.charts" :key="ci" class="chart-card">
                <div class="chart-title">{{ c.title || '图表' }}</div>
                <pre v-if="c.type === 'mermaid'" class="mermaid">{{ c.data }}</pre>
                <img v-else :src="c.data" :alt="c.title" class="chart-img" />
              </div>
            </div>

            <div v-if="m.rag && m.rag.length" class="rag">
              <el-icon><Collection /></el-icon>
              <span class="rag-label">参考知识库</span>
              <span class="rag-list">{{ m.rag.join('、') }}</span>
            </div>

            <el-collapse v-if="m.steps && m.steps.length" class="steps">
              <el-collapse-item title="查看工具执行步骤" name="1">
                <div v-for="(s, idx) in m.steps" :key="idx" class="step">
                  <el-icon v-if="s.status === 'success'" class="ok"><CircleCheck /></el-icon>
                  <el-icon v-else-if="s.status === 'failed'" class="fail"><CircleClose /></el-icon>
                  <el-icon v-else class="spin run"><Loading /></el-icon>
                  <span class="step-name">{{ s.display }}</span>
                  <span class="step-tool">[{{ s.tool }}]</span>
                  <div class="step-result">
                    <el-table v-if="s.result && s.result.kind === 'table'" :data="tableRows(s.result.table)" size="small" border>
                      <el-table-column v-for="c in (s.result.table.columns || [])" :key="c" :prop="c" :label="c" />
                    </el-table>
                    <img v-else-if="s.result && s.result.kind === 'chart' && s.result.chart.type !== 'mermaid'" :src="s.result.chart.data" class="chart" />
                    <pre v-else-if="s.result && s.result.kind === 'chart'">{{ s.result.chart.data }}</pre>
                    <span v-else-if="s.result && s.result.kind === 'text'" class="step-text-preview">{{ stepPreview(s.result.text) }}</span>
                    <span v-else-if="s.result && s.result.error" class="err">{{ s.result.error }}</span>
                  </div>
                </div>
              </el-collapse-item>
            </el-collapse>
          </div>
        </div>
      </div>

      <div v-if="loading" class="msg assistant">
        <span class="avatar assistant"><ChatDotRound /></span>
        <div class="bubble thinking">
          <span class="typing"><i></i><i></i><i></i></span>
          <span class="thinking-text">正在调度工具执行任务</span>
          <div v-for="(s, idx) in liveSteps" :key="idx" class="step">
            <el-icon v-if="s.status === 'success'" class="ok"><CircleCheck /></el-icon>
            <el-icon v-else-if="s.status === 'failed'" class="fail"><CircleClose /></el-icon>
            <el-icon v-else class="spin run"><Loading /></el-icon>
            <span class="step-name">{{ s.display }}</span>
          </div>
        </div>
      </div>
    </div>

    <div class="composer">
      <div class="composer-inner">
        <el-input v-model="input" type="textarea" :autosize="{ minRows: 1, maxRows: 6 }" resize="none"
                  class="composer-input" placeholder="用自然语言描述你的办公任务…"
                  @keydown.enter.exact.prevent="send" @keydown.ctrl.enter.prevent="send" />
        <el-button type="primary" class="send-btn" :disabled="!input.trim() || loading" :loading="loading" @click="send">
          <el-icon><Promotion /></el-icon>
        </el-button>
      </div>
      <div class="composer-hint">Enter 发送 · Shift + Enter 换行</div>
    </div>
  </div>
</template>

<script setup>
import { ref, watch, nextTick } from 'vue'
import { api, chatStream } from '../api.js'
import { CircleCheck, CircleClose, Loading, ChatDotRound, User, ChatRound, Collection, Promotion } from '@element-plus/icons-vue'

const props = defineProps({ conversationId: { type: String, default: null } })
const emit = defineEmits(['created', 'updated'])

const messages = ref([])
const input = ref('')
const loading = ref(false)
const liveSteps = ref([])
const box = ref(null)

const examples = ['纽约现在几点？', '查一下我的客户张三', '查一下特斯拉最新新闻', '今天我有什么日程安排']
function sendExample(ex) { input.value = ex; send() }

function tableRows(t) {
  if (!t || !t.columns) return []
  return (t.rows || []).map((r) => Object.fromEntries(t.columns.map((c, i) => [c, r[i]])))
}

// 步骤面板只预览文本结果的前若干字，避免与最终回答气泡中的完整内容重复
function stepPreview(text) {
  if (!text) return ''
  const max = 120
  return text.length > max ? text.slice(0, max) + ' …（完整内容见下方回复）' : text
}

// 用 mermaid 渲染回答中的流程图（按需动态加载，避免首屏负担）
let _mermaid = null
async function renderMermaid() {
  const nodes = box.value ? box.value.querySelectorAll('pre.mermaid:not([data-rendered])') : []
  if (!nodes.length) return
  try {
    if (!_mermaid) _mermaid = (await import('mermaid')).default
    await _mermaid.run({ nodes })
    nodes.forEach((n) => n.setAttribute('data-rendered', '1'))
  } catch (e) {
    console.warn('mermaid 渲染失败（请确认已安装 mermaid 依赖）', e)
  }
}

watch(() => props.conversationId, async (id) => {
  liveSteps.value = []
  messages.value = []
  if (!id) return
  try {
    const { data } = await api.conversationMessages(id)
    messages.value = data.map((m) => ({
      role: m.role,
      content: m.content,
      steps: m.meta?.steps || [],
      rag: m.meta?.rag || [],
      charts: m.meta?.charts || []
    }))
    await nextTick()
    renderMermaid()
  } catch (e) { /* ignore */ }
  scroll()
}, { immediate: true })

function scroll() {
  nextTick(() => { if (box.value) box.value.scrollTop = box.value.scrollHeight })
}

async function send() {
  const text = input.value.trim()
  if (!text || loading.value) return
  input.value = ''
  loading.value = true
  liveSteps.value = []
  messages.value.push({ role: 'user', content: text })

  const collected = []
  const collectedCharts = []
  let answer = ''
  try {
    await chatStream({ message: text, conversation_id: props.conversationId || undefined }, {
      onPlan: () => { /* plan steps are streamed via step_start/step_result */ },
      onStepStart: (d) => liveSteps.value.push({ display: d.display, status: 'running' }),
      onStepResult: (entry) => {
        const last = liveSteps.value[liveSteps.value.length - 1]
        if (last) { last.status = entry.status; last.tool = entry.tool }
        collected.push(entry)
      },
      onAnswer: (d) => { answer = d.answer },
      onCharts: (d) => { if (d.charts && d.charts.length) collectedCharts.push(...d.charts) },
      onDone: async (d) => {
        const finalAnswer = answer && answer.trim()
          ? answer
          : '抱歉，本次未能生成回答。请稍后重试，或换一种表述方式。'
        messages.value.push({ role: 'assistant', content: finalAnswer, steps: collected, rag: [], charts: collectedCharts })
        await nextTick()
        renderMermaid()
        if (d.conversation_id && d.conversation_id !== props.conversationId) {
          emit('created', d.conversation_id)
        }
        emit('updated')
        scroll()
      },
      onError: (e) => { El_append_error(e.message) }
    })
  } catch (e) {
    El_append_error(e.message)
  } finally {
    loading.value = false
  }
  scroll()
}

function El_append_error(msg) {
  messages.value.push({ role: 'assistant', content: '⚠️ ' + msg, steps: [], rag: [] })
  loading.value = false
  scroll()
}
</script>

<style scoped>
.chat { display: flex; flex-direction: column; height: 100%; background: var(--color-bg); }

/* 消息流：极淡的氛围渐变，避免纯色空洞 */
.thread {
  flex: 1; overflow-y: auto; padding: var(--space-6) 0 var(--space-8);
  background:
    radial-gradient(120% 70% at 50% -12%, var(--el-color-primary-light-9), transparent 62%),
    var(--color-bg);
}

/* 欢迎 / 空状态 */
.welcome { max-width: 680px; margin: 6vh auto 0; padding: 0 var(--space-6); text-align: center; }
.welcome-badge {
  display: inline-flex; align-items: center; justify-content: center;
  width: 64px; height: 64px; border-radius: var(--radius-xl);
  background: linear-gradient(135deg, var(--color-primary), var(--el-color-primary-dark-2));
  color: #fff; box-shadow: var(--shadow-lg);
  margin-bottom: var(--space-5);
}
.welcome-badge svg { width: 32px; height: 32px; }
.welcome-title {
  font-size: var(--font-size-2xl); font-weight: var(--font-weight-semibold);
  color: var(--color-text); letter-spacing: var(--font-letterSpacing-tighter);
  margin: 0 0 var(--space-2);
}
.welcome-sub {
  margin: 0 auto; max-width: 460px; font-size: var(--font-size-base);
  color: var(--color-text-3); line-height: var(--font-lineHeight-relaxed);
}
.welcome-grid {
  display: grid; grid-template-columns: 1fr 1fr; gap: var(--space-3);
  margin-top: var(--space-8); text-align: left;
}
.suggest {
  display: flex; align-items: center; gap: var(--space-3); cursor: pointer;
  padding: var(--space-3) var(--space-4);
  background: var(--color-surface); border: 1px solid var(--color-border);
  border-radius: var(--radius-lg); color: var(--color-text-2);
  box-shadow: var(--shadow-sm);
  transition: transform var(--motion-duration-fast) var(--motion-easing-standard),
              box-shadow var(--motion-duration-fast) var(--motion-easing-standard),
              border-color var(--motion-duration-fast) var(--motion-easing-standard),
              color var(--motion-duration-fast) var(--motion-easing-standard);
}
.suggest:hover {
  transform: translateY(-2px); color: var(--color-text);
  border-color: color-mix(in srgb, var(--color-primary) 40%, var(--color-border));
  box-shadow: var(--shadow-md);
}
.suggest-ico {
  flex: none; display: inline-flex; align-items: center; justify-content: center;
  width: 30px; height: 30px; border-radius: var(--radius-md);
  background: var(--el-color-primary-light-9); color: var(--color-primary);
}
.suggest-ico svg { width: 16px; height: 16px; }
.suggest-text { font-size: var(--font-size-sm); font-weight: var(--font-weight-medium); }

/* 消息行 */
.msg {
  display: flex; align-items: flex-start; gap: var(--space-3);
  margin: 0 auto var(--space-5); padding: 0 var(--space-6);
  max-width: 820px; width: 100%;
  animation: msg-in var(--motion-duration-normal) var(--motion-easing-decelerate) both;
}
.msg.user { flex-direction: row-reverse; }
.avatar {
  flex: none; display: inline-flex; align-items: center; justify-content: center;
  width: 36px; height: 36px; border-radius: var(--radius-md);
  font-size: var(--font-size-sm); font-weight: var(--font-weight-semibold);
  box-shadow: var(--shadow-sm);
}
.avatar.assistant {
  background: linear-gradient(135deg, var(--color-primary), var(--el-color-primary-dark-2));
  color: #fff;
}
.avatar.user { background: var(--color-surface-2); color: var(--color-text-2); border: 1px solid var(--color-border); }

.bubble {
  max-width: 78%; padding: var(--space-3) var(--space-4); border-radius: var(--radius-lg);
  background: var(--color-surface); border: 1px solid var(--color-border);
  box-shadow: var(--shadow-sm); font-size: var(--font-size-base); line-height: var(--font-lineHeight-normal);
  color: var(--color-text);
}
.msg.user .bubble {
  background: linear-gradient(135deg, var(--color-primary), var(--el-color-primary-dark-2));
  color: #fff; border-color: transparent; border-bottom-right-radius: var(--radius-sm);
  box-shadow: var(--shadow-md);
}
.msg.assistant .bubble { border-top-left-radius: var(--radius-sm); }
.bubble pre {
  white-space: pre-wrap; word-break: break-word; font-family: inherit; margin: 0;
  font-size: var(--font-size-base); line-height: var(--font-lineHeight-normal);
}
.msg.user .bubble pre { color: #fff; }

/* RAG 引用 */
.rag {
  display: flex; align-items: center; flex-wrap: wrap; gap: var(--space-2);
  margin-top: var(--space-3); padding: var(--space-2) var(--space-3);
  background: var(--el-color-primary-light-9); border-radius: var(--radius-md);
  font-size: var(--font-size-xs); color: var(--color-primary);
}
.rag-label { font-weight: var(--font-weight-medium); }
.rag .rag-list { color: var(--color-text-2); }

/* 工具步骤 */
.steps { margin-top: var(--space-3); border-top: 1px dashed var(--color-border); padding-top: var(--space-2); }
.steps :deep(.el-collapse) { border: none; }
.steps :deep(.el-collapse-item__header) {
  border: none; background: transparent; height: 32px;
  font-size: var(--font-size-xs); color: var(--color-text-3);
}
.steps :deep(.el-collapse-item__wrap) { border: none; background: transparent; }
.step {
  display: flex; align-items: flex-start; gap: var(--space-2);
  margin: var(--space-2) 0; padding: var(--space-2) var(--space-3);
  background: var(--color-surface-2); border-radius: var(--radius-md);
  font-size: var(--font-size-sm); color: var(--color-text-2);
}
.step .ok { color: var(--color-success); }
.step .fail { color: var(--color-danger); }
.step .run { color: var(--color-primary); }
.step-name { font-weight: var(--font-weight-medium); color: var(--color-text); }
.step-tool { color: var(--color-text-3); font-family: var(--font-mono); font-size: var(--font-size-xs); }
.step-result { margin-left: var(--space-6); width: 100%; }
.chart { max-width: 100%; border: 1px solid var(--color-border); border-radius: var(--radius-md); margin-top: var(--space-2); }
.err { color: var(--color-danger); }
.step-text-preview { white-space: pre-wrap; color: var(--color-text-2); font-size: var(--font-size-xs); }

/* 回答中的图表展示 */
.charts { display: flex; flex-direction: column; gap: var(--space-3); margin-top: var(--space-3); }
.chart-card {
  background: var(--color-surface-2); border: 1px solid var(--color-border);
  border-radius: var(--radius-md); padding: var(--space-3);
}
.chart-title { font-size: var(--font-size-xs); color: var(--color-text-3); margin-bottom: var(--space-2); }
.chart-img { max-width: 100%; border-radius: var(--radius-sm); display: block; }
.chart-card :deep(.mermaid) {
  background: #fff; border-radius: var(--radius-sm); padding: var(--space-3);
  font-family: var(--font-family-mono); overflow-x: auto;
}
.chart-card :deep(.mermaid svg) { max-width: 100%; height: auto; }

/* 加载态：打字指示 + 步骤 */
.thinking { display: flex; flex-direction: column; gap: var(--space-2); }
.typing { display: inline-flex; gap: 4px; align-items: center; }
.typing i {
  width: 6px; height: 6px; border-radius: 50%; background: var(--color-primary);
  animation: blink 1.2s infinite ease-in-out;
}
.typing i:nth-child(2) { animation-delay: .2s; }
.typing i:nth-child(3) { animation-delay: .4s; }
.thinking-text { font-size: var(--font-size-sm); color: var(--color-text-3); }
@keyframes blink {
  0%, 60%, 100% { opacity: .3; transform: translateY(0); }
  30% { opacity: 1; transform: translateY(-3px); }
}
.spin { animation: spin 1s linear infinite; }
@keyframes spin { from { transform: rotate(0); } to { transform: rotate(360deg); } }
@keyframes msg-in { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: translateY(0); } }

/* 输入浮岛 */
.composer { padding: var(--space-4) var(--space-6) var(--space-5); }
.composer-inner {
  display: flex; align-items: flex-end; gap: var(--space-3);
  max-width: 820px; margin: 0 auto; width: 100%;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-xl);
  padding: var(--space-2) var(--space-2) var(--space-2) var(--space-4);
  box-shadow: var(--shadow-md);
  transition: border-color var(--motion-duration-fast) var(--motion-easing-standard),
              box-shadow var(--motion-duration-fast) var(--motion-easing-standard);
}
.composer-inner:focus-within {
  border-color: var(--color-primary);
  box-shadow: 0 0 0 4px color-mix(in srgb, var(--color-primary) 14%, transparent), var(--shadow-md);
}
.composer-input { flex: 1; }
.composer-inner :deep(.el-textarea__inner) {
  border: none !important; box-shadow: none !important; resize: none;
  padding: var(--space-2) 0; background: transparent; font-size: var(--font-size-base);
}
.send-btn {
  flex: none; width: 40px; height: 40px; padding: 0; border-radius: var(--radius-full);
  background: linear-gradient(135deg, var(--color-primary), var(--el-color-primary-dark-2));
  border: none; box-shadow: var(--shadow-md);
  display: inline-flex; align-items: center; justify-content: center;
  transition: transform var(--motion-duration-fast) var(--motion-easing-standard),
              box-shadow var(--motion-duration-fast) var(--motion-easing-standard);
}
.send-btn:hover:not(:disabled) { transform: translateY(-1px); box-shadow: var(--shadow-lg); }
.send-btn:disabled { background: var(--color-surface-2); color: var(--color-text-3); box-shadow: none; }
.send-btn svg { width: 18px; height: 18px; }
.composer-hint {
  max-width: 820px; margin: var(--space-2) auto 0; text-align: center;
  font-size: var(--font-size-xs); color: var(--color-text-3);
}

/* 移动端 */
@media (max-width: 640px) {
  .msg { padding: 0 var(--space-4); }
  .bubble { max-width: 86%; }
  .welcome-grid { grid-template-columns: 1fr; }
  .composer { padding: var(--space-3) var(--space-4) var(--space-4); }
}
</style>

import axios from 'axios'

const BASE = '/api/v1'
const http = axios.create({ baseURL: BASE })

http.interceptors.request.use((cfg) => {
  const token = localStorage.getItem('token')
  if (token) cfg.headers.Authorization = `Bearer ${token}`
  return cfg
})

http.interceptors.response.use(
  (r) => r,
  (err) => {
    if (err.response && err.response.status === 401) {
      localStorage.removeItem('token')
      localStorage.removeItem('user')
      if (location.pathname !== '/login') location.reload()
    }
    return Promise.reject(err)
  }
)

export const api = {
  login: (username, password) =>
    http.post('/auth/login', new URLSearchParams({ username, password }), {
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' }
    }),
  me: () => http.get('/auth/me'),

  listConversations: () => http.get('/chat/conversations'),
  conversationMessages: (id) => http.get(`/chat/conversations/${id}/messages`),
  deleteConversation: (id) => http.delete(`/chat/conversations/${id}`),

  listTools: () => http.get('/tools'),
  uploadKnowledge: (file, meta = {}) => {
    const fd = new FormData()
    fd.append('file', file)
    if (meta.department) fd.append('department', meta.department)
    if (meta.doc_type) fd.append('doc_type', meta.doc_type)
    if (meta.trust_level) fd.append('trust_level', meta.trust_level)
    if (meta.source) fd.append('source', meta.source)
    if (Array.isArray(meta.tags)) meta.tags.forEach((t) => fd.append('tags', t))
    return http.post('/knowledge/upload', fd)
  },
  listDocs: () => http.get('/knowledge'),
  deleteDoc: (id) => http.delete(`/knowledge/${id}`),

  admin: {
    stats: () => http.get('/admin/stats'),
    audit: (params) => http.get('/admin/audit', { params }),
    alerts: () => http.get('/admin/audit/alerts'),
    users: () => http.get('/admin/users'),
    createUser: (p) => http.post('/admin/users', p),
    prompts: () => http.get('/admin/prompts'),
    updatePrompt: (key, body) => http.put(`/admin/prompts/${key}`, body),
    settings: () => http.get('/admin/settings'),
    setExternal: (enabled) => http.post('/admin/settings/external', { enabled })
  }
}

/**
 * Stream a chat request via SSE (fetch ReadableStream).
 * callbacks: onPlan, onStepStart, onStepResult, onAnswer, onDone, onError
 *
 * 防护：AbortController + 30s 总超时，确保任何情况下（后端挂起/网络中断/
 * 模型服务无响应）都不会让前端永久停在"正在调度工具执行任务"。
 */
const STREAM_TIMEOUT_MS = 120000

export async function chatStream(payload, callbacks = {}) {
  const token = localStorage.getItem('token')
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), STREAM_TIMEOUT_MS)
  let finished = false
  const safeFinish = (cb) => {
    if (finished) return
    finished = true
    clearTimeout(timer)
    try { cb && cb() } catch (e) { /* ignore */ }
  }
  try {
    const resp = await fetch(`${BASE}/chat/stream`, {
      method: 'POST',
      signal: controller.signal,
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
      body: JSON.stringify(payload)
    })
    if (!resp.ok) {
      safeFinish(() => callbacks.onError && callbacks.onError(new Error('请求失败: ' + resp.status)))
      return
    }
    const reader = resp.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    while (true) {
      const { value, done } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      let idx
      while ((idx = buffer.indexOf('\n\n')) !== -1) {
        const raw = buffer.slice(0, idx)
        buffer = buffer.slice(idx + 2)
        const ev = parseSSE(raw)
        if (!ev) continue
        dispatch(ev, callbacks)
        if (ev.event === 'done') { safeFinish(() => {}) ; return }
      }
    }
    if (buffer.trim()) {
      const ev = parseSSE(buffer)
      if (ev) dispatch(ev, callbacks)
    }
    safeFinish(() => callbacks.onDone && callbacks.onDone({ answer: '' }))
  } catch (err) {
    if (controller.signal.aborted) {
      safeFinish(() => callbacks.onError && callbacks.onError(new Error('响应超时：服务暂时无响应，请稍后重试')))
    } else {
      safeFinish(() => callbacks.onError && callbacks.onError(err))
    }
  }
}

function parseSSE(raw) {
  let event = 'message'
  const dataLines = []
  for (const line of raw.split('\n')) {
    if (line.startsWith('event:')) event = line.slice(6).trim()
    else if (line.startsWith('data:')) dataLines.push(line.slice(5).trim())
  }
  if (!dataLines.length) return null
  try {
    return { event, data: JSON.parse(dataLines.join('\n')) }
  } catch {
    return null
  }
}

function dispatch(ev, cb) {
  const map = {
    rag: cb.onRag, plan: cb.onPlan, step_start: cb.onStepStart,
    step_result: cb.onStepResult, answer: cb.onAnswer, done: cb.onDone,
    charts: cb.onCharts
  }
  if (map[ev.event]) map[ev.event](ev.data)
}

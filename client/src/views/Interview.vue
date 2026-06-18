<template>
  <div class="interview-page">
    <el-row :gutter="24">
      <!-- Sidebar -->
      <el-col :span="6">
        <el-card class="sidebar-card">
          <template #header>
            <span>📊 面试进度</span>
          </template>
          <div class="sidebar-content">
            <el-progress
              :percentage="store.progress"
              :status="store.isActive ? '' : 'success'"
              :stroke-width="20"
            />
            <div class="stat-item">
              <span class="stat-label">已回答</span>
              <span class="stat-value">{{ store.answeredCount }} / {{ store.maxQuestions }}</span>
            </div>
            <div class="stat-item">
              <span class="stat-label">状态</span>
              <el-tag :type="store.isActive ? 'warning' : 'success'" size="small">
                {{ store.isActive ? '进行中' : '已完成' }}
              </el-tag>
            </div>
            <div v-if="currentQuestionMeta" class="stat-item">
              <span class="stat-label">当前环节</span>
              <el-tag type="primary" size="small">
                {{ skillLabel(currentQuestionMeta.skill_module) }}
              </el-tag>
            </div>
            <div v-if="currentQuestionMeta" class="stat-item">
              <span class="stat-label">难度</span>
              <el-tag size="small">
                {{ difficultyLabel(currentQuestionMeta.difficulty) }}
              </el-tag>
            </div>

            <el-divider />
            <el-button
              type="danger"
              plain
              :disabled="!store.isActive"
              @click="handleEndInterview"
            >
              结束面试
            </el-button>
          </div>
        </el-card>
      </el-col>

      <!-- Chat Area -->
      <el-col :span="18">
        <el-card class="chat-card">
          <div class="chat-container" ref="chatContainer">
            <!-- Messages -->
            <div
              v-for="(msg, i) in messages"
              :key="i"
              :class="['message-row', msg.role]"
            >
              <div class="message-avatar">
                {{ msg.role === 'interviewer' ? '🤖' : '👤' }}
              </div>
              <div :class="['message-bubble', msg.role]">
                <div class="message-content" v-html="renderMarkdown(msg.content)" />
                <div v-if="msg.score !== undefined && msg.score !== null" class="message-score">
                  <el-tag type="warning" size="small">得分: {{ msg.score }}</el-tag>
                  <span v-if="msg.feedback" class="score-feedback">{{ msg.feedback }}</span>
                </div>
              </div>
            </div>

            <!-- Streaming message -->
            <div v-if="streamingText" class="message-row interviewer">
              <div class="message-avatar">🤖</div>
              <div class="message-bubble interviewer">
                <div class="message-content">{{ streamingText }}<span class="cursor">|</span></div>
              </div>
            </div>

            <!-- Loading -->
            <div v-if="waitingForQuestion" class="message-row interviewer">
              <div class="message-avatar">🤖</div>
              <div class="message-bubble interviewer thinking">
                <span class="dot-pulse">面试官正在思考</span>
              </div>
            </div>
          </div>

          <!-- Input -->
          <div class="chat-input-area">
            <el-input
              v-model="userInput"
              type="textarea"
              :rows="3"
              placeholder="输入你的回答..."
              :disabled="!store.isActive || waitingForQuestion"
              @keydown.enter.ctrl="handleSubmitAnswer"
            />
            <div class="input-actions">
              <span class="input-hint">Ctrl + Enter 发送</span>
              <el-button
                type="primary"
                :disabled="!userInput.trim() || waitingForQuestion"
                :loading="submittingAnswer"
                @click="handleSubmitAnswer"
              >
                提交回答
              </el-button>
              <el-button
                v-if="!waitingForQuestion && store.isActive"
                type="success"
                @click="requestNextQuestion"
              >
                下一题
              </el-button>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { ref, nextTick, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { marked } from 'marked'
import { useInterviewStore } from '@/stores/interview'
import {
  getSession,
  submitAnswer,
  endInterview,
  getStreamUrl,
} from '@/api'

const router = useRouter()
const store = useInterviewStore()

const chatContainer = ref<HTMLElement>()
const messages = ref<any[]>([])
const userInput = ref('')
const streamingText = ref('')
const waitingForQuestion = ref(false)
const submittingAnswer = ref(false)
const currentQuestionMeta = ref<any>(null)
const currentQuestionId = ref('')

onMounted(async () => {
  if (!store.sessionId) {
    ElMessage.warning('请先上传简历并开始面试')
    router.push('/')
    return
  }

  // Check session status
  try {
    const res = await getSession(store.sessionId)
    if (res.data.status !== 'active') {
      store.sessionStatus = res.data.status
      ElMessage.info('面试已结束，跳转到报告页')
      router.push('/report')
      return
    }
  } catch {
    ElMessage.error('无法获取面试会话')
    router.push('/')
    return
  }

  // Request first question
  requestNextQuestion()
})

function requestNextQuestion() {
  waitingForQuestion.value = true
  streamingText.value = ''
  currentQuestionMeta.value = null
  currentQuestionId.value = ''

  const url = getStreamUrl(store.sessionId)
  const eventSource = new EventSource(url)

  eventSource.addEventListener('message', (event) => {
    try {
      const data = JSON.parse(event.data)

      if (data.type === 'question_meta') {
        currentQuestionMeta.value = data
        currentQuestionId.value = data.question_id
        waitingForQuestion.value = false
      } else if (data.type === 'token') {
        streamingText.value += data.content
        scrollToBottom()
      } else if (data.type === 'question_complete') {
        // Add to messages
        messages.value.push({
          role: 'interviewer',
          content: streamingText.value,
        })
        streamingText.value = ''
        eventSource.close()
        scrollToBottom()
      } else if (data.type === 'interview_complete') {
        eventSource.close()
        waitingForQuestion.value = false
        ElMessage.info('所有题目已完成！')
        store.sessionStatus = 'completed'
      }
    } catch { /* ignore parse errors */ }
  })

  eventSource.addEventListener('error', () => {
    eventSource.close()
    waitingForQuestion.value = false
    ElMessage.error('连接中断，请刷新重试')
  })
}

async function handleSubmitAnswer() {
  if (!userInput.value.trim() || !currentQuestionId.value) return

  const answerText = userInput.value.trim()
  submittingAnswer.value = true

  try {
    const res = await submitAnswer(store.sessionId, currentQuestionId.value, answerText)

    // Add user message
    messages.value.push({
      role: 'user',
      content: answerText,
    })

    // Add score if available
    if (res.data.status === 'evaluated') {
      // Fetch the latest from report or use response
      messages.value[messages.value.length - 1].score = '已评分'
    }

    userInput.value = ''
    store.incrementAnswered()

    if (!res.data.next_question_ready) {
      ElMessage.success('面试完成！')
      store.sessionStatus = 'completed'
      setTimeout(() => router.push('/report'), 1500)
    } else {
      // Request next question after a brief delay
      setTimeout(requestNextQuestion, 1000)
    }
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '提交失败')
  } finally {
    submittingAnswer.value = false
  }
}

async function handleEndInterview() {
  try {
    await ElMessageBox.confirm('确定要结束面试吗？结束后可查看评分报告。', '提示', {
      confirmButtonText: '确定',
      cancelButtonText: '继续面试',
    })
    await endInterview(store.sessionId)
    store.sessionStatus = 'completed'
    ElMessage.success('面试已结束')
    router.push('/report')
  } catch { /* cancelled */ }
}

function scrollToBottom() {
  nextTick(() => {
    if (chatContainer.value) {
      chatContainer.value.scrollTop = chatContainer.value.scrollHeight
    }
  })
}

function skillLabel(skill: string): string {
  const map: Record<string, string> = {
    warmup: '热身',
    technical_qa: '技术问答',
    behavioral: '行为面试',
    system_design: '系统设计',
    coding_challenge: '编程挑战',
  }
  return map[skill] || skill
}

function difficultyLabel(d: string): string {
  const map: Record<string, string> = {
    easy: '简单',
    medium: '中等',
    hard: '困难',
  }
  return map[d] || d
}

function renderMarkdown(text: string): string {
  if (!text) return ''
  return marked.parse(text, { breaks: true }) as string
}
</script>

<style scoped>
.interview-page {
  height: calc(100vh - 112px);
}

.sidebar-card {
  height: 100%;
}

.sidebar-content {
  text-align: center;
}

.stat-item {
  margin-top: 16px;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.stat-label {
  color: #909399;
  font-size: 13px;
}

.stat-value {
  font-weight: 600;
  color: #303133;
}

.chat-card {
  height: 100%;
  display: flex;
  flex-direction: column;
}

.chat-container {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
  min-height: 400px;
  max-height: calc(100vh - 320px);
}

.message-row {
  display: flex;
  gap: 12px;
  margin-bottom: 20px;
}

.message-row.interviewer {
  flex-direction: row;
}

.message-row.user {
  flex-direction: row-reverse;
}

.message-avatar {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 20px;
  flex-shrink: 0;
}

.message-bubble {
  max-width: 75%;
  padding: 12px 16px;
  border-radius: 12px;
  font-size: 15px;
  line-height: 1.6;
}

.message-bubble.interviewer {
  background: #f0f2f5;
  border-bottom-left-radius: 4px;
}

.message-bubble.user {
  background: linear-gradient(135deg, #667eea, #764ba2);
  color: white;
  border-bottom-right-radius: 4px;
}

.message-bubble.thinking {
  padding: 8px 16px;
  background: #fafafa;
  border: 1px dashed #ddd;
}

.message-score {
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px solid #e8e8e8;
  display: flex;
  align-items: center;
  gap: 8px;
}

.score-feedback {
  font-size: 13px;
  color: #909399;
}

.cursor {
  animation: blink 1s step-end infinite;
  color: #667eea;
}

@keyframes blink {
  50% { opacity: 0; }
}

.dot-pulse {
  color: #909399;
  font-style: italic;
}

.chat-input-area {
  padding: 16px;
  border-top: 1px solid #ebeef5;
  background: #fafafa;
}

.input-actions {
  margin-top: 12px;
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 12px;
}

.input-hint {
  font-size: 12px;
  color: #c0c4cc;
  margin-right: auto;
}

.message-content :deep(p) {
  margin: 4px 0;
}

.message-content :deep(code) {
  background: rgba(0,0,0,0.06);
  padding: 2px 6px;
  border-radius: 3px;
  font-size: 13px;
}

.message-content :deep(pre) {
  background: #282c34;
  color: #abb2bf;
  padding: 12px;
  border-radius: 8px;
  overflow-x: auto;
  font-size: 13px;
}
</style>

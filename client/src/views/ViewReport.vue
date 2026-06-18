<template>
  <div class="report-page">
    <el-row :gutter="24">
      <!-- History Sidebar -->
      <el-col :span="6">
        <el-card class="history-card">
          <template #header>
            <span>📋 历史面试</span>
          </template>
          <div v-if="historyList.length > 0" class="history-list">
            <div
              v-for="item in historyList"
              :key="item.session_id"
              :class="['history-item', { active: activeSessionId === item.session_id }]"
              @click="loadReport(item.session_id)"
            >
              <div class="history-date">{{ formatDate(item.started_at) }}</div>
              <el-tag :type="item.status === 'completed' ? 'success' : 'info'" size="small">
                {{ item.status === 'completed' ? '已完成' : '进行中' }}
              </el-tag>
              <span class="history-count">{{ item.question_count }} 题</span>
            </div>
          </div>
          <el-empty v-else description="暂无历史面试" :image-size="60" />
        </el-card>
      </el-col>

      <!-- Main Report -->
      <el-col :span="18">
        <el-card class="report-card">
          <template #header>
            <div class="card-header">
              <span>📊 面试评估报告</span>
              <el-button type="primary" plain @click="$router.push('/')">
                重新开始
              </el-button>
            </div>
          </template>

          <div v-if="loading" class="loading-container">
            <el-skeleton :rows="8" animated />
          </div>

          <div v-else-if="!activeSessionId" class="empty-state">
            <el-empty description="选择一个历史面试或开始新面试">
              <el-button type="primary" @click="$router.push('/')">上传简历开始面试</el-button>
            </el-empty>
          </div>

          <div v-else-if="report" class="report-content">
            <!-- Overall Score -->
            <div class="overall-score-section">
              <h2>综合评分</h2>
              <div class="score-display">
                <el-progress
                  type="dashboard"
                  :percentage="report.overall_score || 0"
                  :color="scoreColor(report.overall_score)"
                  :stroke-width="16"
                  :width="200"
                >
                  <template #default="{ percentage }">
                    <span class="score-number">{{ percentage }}</span>
                    <span class="score-label">总分</span>
                  </template>
                </el-progress>
                <div class="score-summary">
                  <div class="summary-item">
                    <span class="num">{{ report.evaluated_questions }}</span>
                    <span class="txt">已评估 / {{ report.total_questions }} 题</span>
                  </div>
                </div>
              </div>
            </div>

            <el-divider />

            <!-- Dimension Breakdown -->
            <div v-if="report.dimension_breakdown && Object.keys(report.dimension_breakdown).length > 0" class="section">
              <h3>维度分析</h3>
              <div ref="radarChart" class="chart-container"></div>
            </div>
            <div v-else class="section">
              <h3>维度分析</h3>
              <el-empty description="暂无维度数据" :image-size="80" />
            </div>

            <el-divider />

            <!-- Skill Breakdown -->
            <div v-if="report.skill_breakdown" class="section">
              <h3>环节分析</h3>
              <div class="skill-bars">
                <div
                  v-for="(score, skill) in report.skill_breakdown"
                  :key="skill"
                  class="skill-bar-item"
                >
                  <div class="skill-bar-label">
                    <span>{{ skillLabel(skill) }}</span>
                    <span class="skill-bar-score">{{ score }}</span>
                  </div>
                  <el-progress
                    :percentage="score"
                    :color="scoreColor(score)"
                    :stroke-width="14"
                  />
                </div>
              </div>
            </div>

            <el-divider />

            <!-- Questions Detail -->
            <div class="section">
              <h3>逐题回顾</h3>
              <el-collapse accordion>
                <el-collapse-item
                  v-for="(q, i) in report.questions"
                  :key="q.question_id"
                  :name="i"
                >
                  <template #title>
                    <div class="question-title">
                      <el-tag :type="qTypeTag(q.question_type)" size="small">
                        {{ qTypeLabel(q.question_type) }}
                      </el-tag>
                      <span class="q-text">{{ q.question_text.substring(0, 80) }}...</span>
                      <el-tag v-if="q.score !== null" type="warning" size="small">
                        {{ q.score }} 分
                      </el-tag>
                      <el-tag v-else type="info" size="small">不计分</el-tag>
                    </div>
                  </template>
                  <div class="question-detail">
                    <p><strong>问题：</strong>{{ q.question_text }}</p>
                    <p><strong>你的回答：</strong>{{ q.user_answer || '(未回答)' }}</p>
                    <p v-if="q.feedback"><strong>反馈：</strong>{{ q.feedback }}</p>
                    <div v-if="q.score_breakdown" class="breakdown-detail">
                      <strong>详细评分：</strong>
                      <div
                        v-for="(v, k) in q.score_breakdown"
                        :key="k"
                        class="breakdown-row"
                      >
                        <span>{{ dimLabel(k) }}</span>
                        <el-progress
                          :percentage="v"
                          :stroke-width="6"
                          :color="scoreColor(v)"
                          style="flex: 1; margin: 0 12px;"
                        />
                        <span>{{ v }}</span>
                      </div>
                    </div>
                  </div>
                </el-collapse-item>
              </el-collapse>
            </div>

            <el-divider />

            <!-- Improvement Suggestions -->
            <div v-if="report.improvement_suggestions?.length" class="section">
              <h3>改进建议</h3>
              <div
                v-for="(item, i) in report.improvement_suggestions"
                :key="i"
                class="suggestion-item"
              >
                <el-tag :type="priorityColor(item.priority)" effect="dark">
                  {{ priorityLabel(item.priority) }}
                </el-tag>
                <strong>{{ item.area }}</strong>
                <p>{{ item.suggestion }}</p>
              </div>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, nextTick, watch } from 'vue'
import { getReport, getInterviewHistory } from '@/api'
import { useInterviewStore } from '@/stores/interview'
import * as echarts from 'echarts'

const store = useInterviewStore()

const loading = ref(false)
const report = ref<any>(null)
const radarChart = ref<HTMLElement>()
const historyList = ref<any[]>([])
const activeSessionId = ref(store.sessionId || '')

onMounted(async () => {
  // Load interview history
  try {
    const res = await getInterviewHistory()
    historyList.value = res.data.sessions || []
  } catch { /* guest user */ }

  // Load last session's report
  if (activeSessionId.value) {
    await loadReport(activeSessionId.value)
  } else if (historyList.value.length > 0) {
    await loadReport(historyList.value[0].session_id)
  }
})

async function loadReport(sessionId: string) {
  activeSessionId.value = sessionId
  store.sessionId = sessionId  // persist
  loading.value = true
  try {
    const res = await getReport(sessionId)
    report.value = res.data
  } catch {
    report.value = null
  } finally {
    loading.value = false
  }
}

// Watch for dimension data and render radar chart
watch(
  () => report.value?.dimension_breakdown,
  (dims) => {
    if (dims && Object.keys(dims).length > 0) {
      nextTick(() => renderRadarChart())
    }
  },
)

function renderRadarChart() {
  if (!radarChart.value || !report.value?.dimension_breakdown) return

  const dims = report.value.dimension_breakdown
  const existing = echarts.getInstanceByDom(radarChart.value)
  if (existing) existing.dispose()

  const chart = echarts.init(radarChart.value)
  chart.setOption({
    radar: {
      indicator: Object.keys(dims).map(k => ({
        name: dimLabel(k),
        max: 100,
      })),
      center: ['50%', '55%'],
      radius: '75%',
    },
    series: [{
      type: 'radar',
      data: [{
        value: Object.values(dims),
        name: '得分',
        areaStyle: { color: 'rgba(102, 126, 234, 0.2)' },
        lineStyle: { color: '#667eea', width: 2 },
        itemStyle: { color: '#667eea' },
      }],
    }],
  })
}

function formatDate(iso: string | null): string {
  if (!iso) return '未知'
  const d = new Date(iso)
  return `${d.getMonth() + 1}/${d.getDate()} ${d.getHours()}:${String(d.getMinutes()).padStart(2, '0')}`
}

function scoreColor(score: number | null): string {
  if (!score || score < 60) return '#f56c6c'
  if (score < 80) return '#e6a23c'
  return '#67c23a'
}

function priorityColor(p: string): string {
  const map: Record<string, string> = { high: 'danger', medium: 'warning', low: 'info' }
  return map[p] || 'info'
}

function priorityLabel(p: string): string {
  const map: Record<string, string> = { high: '高优先级', medium: '中优先级', low: '低优先级' }
  return map[p] || p
}

function qTypeTag(t: string): string {
  const map: Record<string, string> = {
    technical: '', behavioral: 'success', system_design: 'warning',
    coding: 'danger', warmup: 'info',
  }
  return map[t] || 'info'
}

function qTypeLabel(t: string): string {
  const map: Record<string, string> = {
    technical: '技术', behavioral: '行为', system_design: '设计',
    coding: '编程', warmup: '热身',
  }
  return map[t] || t
}

function skillLabel(s: string): string {
  const map: Record<string, string> = {
    warmup: '热身', technical_qa: '技术问答', behavioral: '行为面试',
    system_design: '系统设计', coding_challenge: '编程挑战',
  }
  return map[s] || s
}

function dimLabel(d: string): string {
  const map: Record<string, string> = {
    technical_accuracy: '技术准确度',
    depth_breadth: '深度与广度',
    clarity: '表达清晰度',
    practical_experience: '实践经验',
  }
  return map[d] || d
}
</script>

<style scoped>
.report-page {
  max-width: 1200px;
  margin: 0 auto;
}

.history-card {
  position: sticky;
  top: 24px;
}

.history-list {
  max-height: 500px;
  overflow-y: auto;
}

.history-item {
  padding: 10px 12px;
  margin-bottom: 6px;
  border-radius: 8px;
  cursor: pointer;
  border: 1px solid #ebeef5;
  transition: all 0.2s;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}

.history-item:hover {
  background: #f0f2f5;
}

.history-item.active {
  background: #ecf5ff;
  border-color: #667eea;
}

.history-date {
  font-size: 13px;
  color: #606266;
  width: 100%;
}

.history-count {
  font-size: 12px;
  color: #909399;
  margin-left: auto;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.card-header span {
  font-size: 18px;
  font-weight: 600;
}

.report-content {
  padding: 8px 0;
}

.overall-score-section {
  text-align: center;
}

.overall-score-section h2 {
  margin-bottom: 24px;
  color: #303133;
}

.score-display {
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 48px;
}

.score-number {
  font-size: 48px;
  font-weight: 700;
  color: #303133;
}

.score-label {
  font-size: 14px;
  color: #909399;
  display: block;
}

.summary-item {
  text-align: center;
}

.summary-item .num {
  font-size: 36px;
  font-weight: 700;
  color: #667eea;
  display: block;
}

.summary-item .txt {
  font-size: 13px;
  color: #909399;
}

.section {
  margin: 24px 0;
}

.section h3 {
  font-size: 17px;
  font-weight: 600;
  margin-bottom: 16px;
  color: #303133;
}

.chart-container {
  width: 100%;
  height: 360px;
}

.skill-bars {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.skill-bar-item {
  padding: 8px 0;
}

.skill-bar-label {
  display: flex;
  justify-content: space-between;
  margin-bottom: 8px;
  font-size: 14px;
}

.skill-bar-score {
  font-weight: 600;
  color: #667eea;
}

.question-title {
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;
}

.q-text {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.question-detail {
  padding: 8px 16px;
  line-height: 1.8;
}

.breakdown-detail {
  margin-top: 12px;
}

.breakdown-row {
  display: flex;
  align-items: center;
  margin: 6px 0;
  font-size: 13px;
}

.breakdown-row span:first-child {
  width: 100px;
  flex-shrink: 0;
}

.suggestion-item {
  padding: 12px 16px;
  margin-bottom: 12px;
  background: #fafafa;
  border-radius: 8px;
  border-left: 3px solid #667eea;
}

.suggestion-item strong {
  margin-left: 8px;
}

.suggestion-item p {
  margin-top: 6px;
  color: #606266;
  font-size: 14px;
}

.loading-container {
  padding: 40px;
}

.empty-state {
  padding: 60px;
}
</style>

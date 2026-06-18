<template>
  <div class="upload-page">
    <el-card class="upload-card">
      <template #header>
        <div class="card-header">
          <span>📄 上传简历</span>
        </div>
      </template>

      <el-upload
        class="upload-area"
        drag
        :auto-upload="false"
        :limit="1"
        accept=".pdf"
        :on-change="handleFileChange"
        :on-remove="handleFileRemove"
      >
        <div class="upload-placeholder">
          <el-icon :size="64" color="#667eea"><UploadFilled /></el-icon>
          <div class="upload-text">将 PDF 简历拖拽到此处，或点击上传</div>
          <div class="upload-hint">仅支持 PDF 格式，文件大小不超过 10MB</div>
        </div>
      </el-upload>

      <div class="upload-actions">
        <el-button
          type="primary"
          size="large"
          :loading="uploading"
          :disabled="!selectedFile"
          @click="handleUpload"
        >
          {{ uploading ? '正在解析简历...' : '开始解析' }}
        </el-button>
      </div>

      <!-- Analysis Result -->
      <div v-if="resumeData" class="analysis-result">
        <el-alert
          :type="resumeData.status === 'completed' ? 'success' : 'warning'"
          :title="resumeData.status === 'completed' ? '简历解析完成！' : '解析中...'"
          :closable="false"
          show-icon
        />

        <div v-if="resumeData.status === 'completed'" class="resume-detail">
          <!-- Personal Info -->
          <div v-if="resumeData.personal_info" class="info-section">
            <h3>基本信息</h3>
            <el-descriptions :column="2" border size="small">
              <el-descriptions-item label="姓名">
                {{ resumeData.personal_info.name || '未知' }}
              </el-descriptions-item>
              <el-descriptions-item label="邮箱">
                {{ resumeData.personal_info.email || '未知' }}
              </el-descriptions-item>
              <el-descriptions-item label="工作经验">
                {{ resumeData.years_experience || '未知' }} 年
              </el-descriptions-item>
            </el-descriptions>
          </div>

          <!-- Tech Stack -->
          <div class="info-section">
            <h3>技术栈</h3>
            <div class="tech-tags">
              <el-tag
                v-for="(tech, i) in resumeData.tech_stack"
                :key="i"
                :type="getTagType(tech.proficiency)"
                effect="dark"
                size="large"
                class="tech-tag"
              >
                {{ tech.name }}
                <span class="tech-level">({{ proficiencyLabel(tech.proficiency) }})</span>
              </el-tag>
              <span v-if="!resumeData.tech_stack?.length" class="no-data">无数据</span>
            </div>
          </div>

          <!-- Start Interview -->
          <div class="start-interview-section">
            <el-divider />
            <div class="interview-options">
              <h3>开始面试</h3>
              <el-form :inline="true">
                <el-form-item label="难度">
                  <el-select v-model="difficulty" style="width: 140px">
                    <el-option label="简单" value="easy" />
                    <el-option label="中等" value="medium" />
                    <el-option label="困难" value="hard" />
                  </el-select>
                </el-form-item>
                <el-form-item label="题目数量">
                  <el-input-number v-model="questionCount" :min="5" :max="20" />
                </el-form-item>
              </el-form>
              <el-button
                type="success"
                size="large"
                :loading="startingInterview"
                @click="handleStartInterview"
              >
                🚀 开始面试
              </el-button>
            </div>
          </div>
        </div>
      </div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { UploadFilled } from '@element-plus/icons-vue'
import { uploadResume, getResumeAnalysis, startInterview, getMyResume } from '@/api'
import { useInterviewStore } from '@/stores/interview'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const store = useInterviewStore()
const authStore = useAuthStore()

const selectedFile = ref<File | null>(null)
const uploading = ref(false)
const startingInterview = ref(false)
const resumeData = ref<any>(null)
const difficulty = ref('medium')
const questionCount = ref(10)

// Auto-load bound resume on mount
onMounted(async () => {
  if (!authStore.isLoggedIn) return

  await authStore.refreshProfile()
  if (authStore.hasResume && authStore.user?.latest_resume_id) {
    try {
      const res = await getResumeAnalysis(authStore.user.latest_resume_id)
      resumeData.value = res.data
      store.setResume(authStore.user.latest_resume_id)
      ElMessage.success(`已自动加载绑定的简历 — ${authStore.user.tech_stack?.map((t: any) => t.name).join(', ') || '无技术栈数据'}`)
    } catch {
      // Stale resume ID, let user re-upload
    }
  }
})

function handleFileChange(file: any) {
  selectedFile.value = file.raw
}

function handleFileRemove() {
  selectedFile.value = null
  resumeData.value = null
}

async function handleUpload() {
  if (!selectedFile.value) return
  uploading.value = true
  try {
    const res = await uploadResume(selectedFile.value)
    const resumeId = res.data.resume_id
    store.setResume(resumeId)

    ElMessage.success('简历上传成功，正在解析...')

    // Poll until completed
    let retries = 30
    while (retries-- > 0) {
      await new Promise(r => setTimeout(r, 2000))
      const analysis = await getResumeAnalysis(resumeId)
      if (analysis.data.status === 'completed' || analysis.data.status === 'failed') {
        resumeData.value = analysis.data
        // Refresh auth profile to update bound resume
        if (analysis.data.status === 'completed') {
          authStore.refreshProfile()
        }
        break
      }
    }
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '上传失败')
  } finally {
    uploading.value = false
  }
}

async function handleStartInterview() {
  if (!store.resumeId) return
  startingInterview.value = true
  try {
    const res = await startInterview({
      resume_id: store.resumeId,
      difficulty: difficulty.value,
      question_count: questionCount.value,
    })
    store.setSession(res.data.session_id, res.data.status, questionCount.value)
    ElMessage.success(res.data.message)
    router.push('/interview')
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '启动面试失败')
  } finally {
    startingInterview.value = false
  }
}

function getTagType(proficiency: string): string {
  const map: Record<string, string> = {
    expert: 'danger',
    advanced: 'warning',
    intermediate: '',
    beginner: 'info',
  }
  return map[proficiency] || 'info'
}

function proficiencyLabel(p: string): string {
  const map: Record<string, string> = {
    expert: '专家',
    advanced: '精通',
    intermediate: '熟练',
    beginner: '了解',
  }
  return map[p] || p
}
</script>

<style scoped>
.upload-page {
  max-width: 800px;
  margin: 0 auto;
}

.upload-card {
  margin-top: 24px;
}

.card-header span {
  font-size: 18px;
  font-weight: 600;
}

.upload-placeholder {
  padding: 40px;
  text-align: center;
}

.upload-text {
  margin-top: 16px;
  font-size: 16px;
  color: #606266;
}

.upload-hint {
  margin-top: 8px;
  font-size: 13px;
  color: #909399;
}

.upload-actions {
  margin-top: 24px;
  text-align: center;
}

.analysis-result {
  margin-top: 24px;
}

.resume-detail {
  margin-top: 20px;
}

.info-section {
  margin-top: 20px;
}

.info-section h3 {
  font-size: 16px;
  font-weight: 600;
  margin-bottom: 12px;
  color: #303133;
}

.tech-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.tech-tag {
  font-size: 14px;
  padding: 4px 12px;
}

.tech-level {
  opacity: 0.8;
  font-size: 12px;
}

.no-data {
  color: #909399;
}

.start-interview-section {
  margin-top: 8px;
}

.start-interview-section h3 {
  font-size: 16px;
  font-weight: 600;
  margin-bottom: 16px;
}

.interview-options {
  text-align: center;
}
</style>

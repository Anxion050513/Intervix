<template>
  <div class="login-page">
    <el-card class="login-card">
      <template #header>
        <div class="card-header">
          <span>{{ isRegister ? '注册新账号' : '登录' }}</span>
        </div>
      </template>

      <el-form
        ref="formRef"
        :model="form"
        :rules="rules"
        label-position="top"
        @keydown.enter="handleSubmit"
      >
        <el-form-item v-if="isRegister" label="姓名" prop="name">
          <el-input v-model="form.name" placeholder="请输入姓名" />
        </el-form-item>

        <el-form-item label="邮箱" prop="email">
          <el-input v-model="form.email" type="email" placeholder="请输入邮箱" />
        </el-form-item>

        <el-form-item label="密码" prop="password">
          <el-input
            v-model="form.password"
            type="password"
            placeholder="请输入密码（至少6位）"
            show-password
          />
        </el-form-item>

        <el-form-item v-if="isRegister" label="确认密码" prop="confirmPassword">
          <el-input
            v-model="form.confirmPassword"
            type="password"
            placeholder="再次输入密码"
            show-password
          />
        </el-form-item>
      </el-form>

      <div class="login-actions">
        <el-button
          type="primary"
          size="large"
          :loading="loading"
          style="width: 100%"
          @click="handleSubmit"
        >
          {{ isRegister ? '注册' : '登录' }}
        </el-button>
      </div>

      <div class="switch-mode">
        <span v-if="!isRegister">
          还没有账号？
          <el-button type="primary" link @click="isRegister = true">去注册</el-button>
        </span>
        <span v-else>
          已有账号？
          <el-button type="primary" link @click="isRegister = false">去登录</el-button>
        </span>
      </div>

      <el-alert
        style="margin-top: 16px"
        title="登录后上传简历将自动绑定到你的账号，下次使用无需重复上传。"
        type="info"
        :closable="false"
      />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const authStore = useAuthStore()

const isRegister = ref(false)
const loading = ref(false)

const form = reactive({
  name: '',
  email: '',
  password: '',
  confirmPassword: '',
})

const rules = {
  name: [{ required: true, message: '请输入姓名', trigger: 'blur' }],
  email: [
    { required: true, message: '请输入邮箱', trigger: 'blur' },
    { type: 'email', message: '邮箱格式不正确', trigger: 'blur' },
  ],
  password: [
    { required: true, message: '请输入密码', trigger: 'blur' },
    { min: 6, message: '密码至少6位', trigger: 'blur' },
  ],
  confirmPassword: [
    { required: true, message: '请再次输入密码', trigger: 'blur' },
    {
      validator: (_rule: any, value: string, callback: Function) => {
        if (value !== form.password) {
          callback(new Error('两次密码不一致'))
        } else {
          callback()
        }
      },
      trigger: 'blur',
    },
  ],
}

async function handleSubmit() {
  if (loading.value) return

  // Basic validation
  if (!form.email || !form.password) {
    ElMessage.warning('请填写邮箱和密码')
    return
  }
  if (isRegister.value && !form.name) {
    ElMessage.warning('请填写姓名')
    return
  }
  if (isRegister.value && form.password !== form.confirmPassword) {
    ElMessage.warning('两次密码不一致')
    return
  }

  loading.value = true
  try {
    if (isRegister.value) {
      await authStore.register(form.name, form.email, form.password)
      ElMessage.success('注册成功！')
    } else {
      await authStore.login(form.email, form.password)
      ElMessage.success(`欢迎回来，${authStore.user?.name || '用户'}！`)
    }
    router.push('/')
  } catch (e: any) {
    const msg = e.response?.data?.detail || '操作失败，请重试'
    ElMessage.error(msg)
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-page {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: calc(100vh - 160px);
}

.login-card {
  width: 420px;
}

.card-header span {
  font-size: 18px;
  font-weight: 600;
}

.login-actions {
  margin-top: 8px;
}

.switch-mode {
  margin-top: 16px;
  text-align: center;
  font-size: 14px;
  color: #909399;
}
</style>

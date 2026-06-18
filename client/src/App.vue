<template>
  <div id="app-container">
    <el-container>
      <el-header class="app-header">
        <div class="header-left">
          <h1>AI 智能面试官</h1>
          <span class="header-subtitle">模拟真实面试，提升面试能力</span>
        </div>
        <div class="header-right">
          <el-button type="text" @click="$router.push('/')">上传简历</el-button>
          <el-button type="text" @click="$router.push('/interview')">开始面试</el-button>
          <el-button type="text" @click="$router.push('/report')">查看报告</el-button>

          <el-divider direction="vertical" />

          <!-- User area -->
          <template v-if="authStore.isLoggedIn && authStore.user">
            <el-dropdown trigger="click">
              <span class="user-info">
                👤 {{ authStore.user.name }}
                <el-tag v-if="authStore.hasResume" size="small" type="success" effect="dark">
                  已绑定简历
                </el-tag>
              </span>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item disabled>
                    邮箱: {{ authStore.user.email }}
                  </el-dropdown-item>
                  <el-dropdown-item v-if="authStore.hasResume" disabled>
                    技术栈: {{ authStore.user.tech_stack?.map((t: any) => t.name).join(', ') || '无' }}
                  </el-dropdown-item>
                  <el-dropdown-item divided @click="handleLogout">
                    退出登录
                  </el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </template>
          <template v-else>
            <el-button type="text" @click="$router.push('/login')">登录 / 注册</el-button>
          </template>
        </div>
      </el-header>
      <el-main>
        <router-view />
      </el-main>
    </el-container>
  </div>
</template>

<script setup lang="ts">
import { onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const authStore = useAuthStore()

onMounted(() => {
  authStore.initFromStorage()
  if (authStore.isLoggedIn) {
    authStore.refreshProfile()
  }
})

function handleLogout() {
  authStore.logout()
  router.push('/')
}
</script>

<style>
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
  background-color: #f5f7fa;
}

.app-header {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 32px;
  height: 64px !important;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15);
}

.header-left h1 {
  font-size: 22px;
  font-weight: 700;
}

.header-subtitle {
  font-size: 13px;
  opacity: 0.85;
  margin-left: 16px;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 4px;
}

.header-right .el-button {
  color: white;
  font-size: 14px;
}

.header-right .el-button:hover {
  background: rgba(255, 255, 255, 0.15);
}

.header-right .el-divider--vertical {
  border-color: rgba(255, 255, 255, 0.3);
  height: 20px;
  margin: 0 8px;
}

.user-info {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  color: white;
  font-size: 14px;
  padding: 4px 8px;
  border-radius: 4px;
}

.user-info:hover {
  background: rgba(255, 255, 255, 0.15);
}

.el-main {
  max-width: 1200px;
  margin: 0 auto;
  width: 100%;
  padding: 24px;
}
</style>

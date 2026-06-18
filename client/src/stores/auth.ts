import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { loginApi, registerApi, getMyProfile } from '@/api'

interface UserProfile {
  id: string
  name: string
  email: string
  has_resume: boolean
  latest_resume_id: string | null
  tech_stack: any[]
  years_experience: number | null
}

export const useAuthStore = defineStore('auth', () => {
  const token = ref(localStorage.getItem('auth_token') || '')
  const user = ref<UserProfile | null>(null)

  const isLoggedIn = computed(() => !!token.value)
  const hasResume = computed(() => user.value?.has_resume ?? false)

  // Auto-restore from localStorage
  function initFromStorage() {
    const saved = localStorage.getItem('auth_user')
    if (saved) {
      try {
        user.value = JSON.parse(saved)
      } catch { /* ignore */ }
    }
  }

  async function login(email: string, password: string) {
    const res = await loginApi(email, password)
    token.value = res.data.access_token
    user.value = res.data.user
    localStorage.setItem('auth_token', token.value)
    localStorage.setItem('auth_user', JSON.stringify(user.value))
    return user.value
  }

  async function register(name: string, email: string, password: string) {
    const res = await registerApi(name, email, password)
    token.value = res.data.access_token
    user.value = res.data.user
    localStorage.setItem('auth_token', token.value)
    localStorage.setItem('auth_user', JSON.stringify(user.value))
    return user.value
  }

  async function refreshProfile() {
    if (!token.value) return
    try {
      const res = await getMyProfile()
      user.value = res.data
      localStorage.setItem('auth_user', JSON.stringify(user.value))
    } catch {
      // Token expired
      logout()
    }
  }

  function logout() {
    token.value = ''
    user.value = null
    localStorage.removeItem('auth_token')
    localStorage.removeItem('auth_user')
  }

  return {
    token,
    user,
    isLoggedIn,
    hasResume,
    initFromStorage,
    login,
    register,
    refreshProfile,
    logout,
  }
})

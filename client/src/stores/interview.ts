import { defineStore } from 'pinia'
import { ref, computed, watch } from 'vue'

export const useInterviewStore = defineStore('interview', () => {
  // State — restore sessionId from localStorage if available
  const resumeId = ref('')
  const sessionId = ref(localStorage.getItem('last_session_id') || '')
  const sessionStatus = ref('')
  const currentQuestion = ref<any>(null)
  const questionCount = ref(0)
  const answeredCount = ref(0)
  const maxQuestions = ref(10)

  // Persist sessionId to localStorage so it survives refresh/re-login
  watch(sessionId, (val) => {
    if (val) {
      localStorage.setItem('last_session_id', val)
    }
  })

  // Computed
  const isActive = computed(() => sessionStatus.value === 'active')
  const progress = computed(() =>
    maxQuestions.value > 0
      ? Math.round((answeredCount.value / maxQuestions.value) * 100)
      : 0
  )

  // Actions
  function setResume(id: string) {
    resumeId.value = id
  }

  function setSession(id: string, status: string, max: number = 10) {
    sessionId.value = id
    sessionStatus.value = status
    maxQuestions.value = max
  }

  function setCurrentQuestion(question: any) {
    currentQuestion.value = question
  }

  function incrementAnswered() {
    answeredCount.value++
    questionCount.value++
  }

  function reset() {
    resumeId.value = ''
    sessionId.value = ''
    sessionStatus.value = ''
    currentQuestion.value = null
    questionCount.value = 0
    answeredCount.value = 0
    localStorage.removeItem('last_session_id')
  }

  return {
    resumeId,
    sessionId,
    sessionStatus,
    currentQuestion,
    questionCount,
    answeredCount,
    maxQuestions,
    isActive,
    progress,
    setResume,
    setSession,
    setCurrentQuestion,
    incrementAnswered,
    reset,
  }
})

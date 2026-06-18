import axios from 'axios'

const api = axios.create({
  baseURL: '/api/v1',
  timeout: 60000,
  headers: {
    'Content-Type': 'application/json',
  },
})

// Request interceptor — attach JWT token
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('auth_token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// Response interceptor — handle 401
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      // Token expired or invalid — redirect to login
      localStorage.removeItem('auth_token')
      localStorage.removeItem('auth_user')
      if (window.location.pathname !== '/login') {
        window.location.href = '/login'
      }
    }
    const message = error.response?.data?.detail || error.message || 'Request failed'
    console.error('API Error:', message)
    return Promise.reject(error)
  }
)

// --- Auth ---
export async function loginApi(email: string, password: string) {
  return api.post('/auth/login', { email, password })
}

export async function registerApi(name: string, email: string, password: string) {
  return api.post('/auth/register', { name, email, password })
}

export async function getMyProfile() {
  return api.get('/auth/me')
}

// --- Resume ---
export async function uploadResume(file: File) {
  const formData = new FormData()
  formData.append('file', file)
  return api.post('/resume/upload', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
}

export async function getMyResume() {
  return api.get('/resume/my')
}

export async function getResume(resumeId: string) {
  return api.get(`/resume/${resumeId}`)
}

export async function getResumeAnalysis(resumeId: string) {
  return api.get(`/resume/${resumeId}/analysis`)
}

// --- Interview ---
export async function startInterview(data: {
  resume_id: string
  skill_modules?: string[]
  difficulty?: string
  question_count?: number
}) {
  return api.post('/interview/start', data)
}

export async function getSession(sessionId: string) {
  return api.get(`/interview/${sessionId}`)
}

export async function submitAnswer(sessionId: string, questionId: string, answerText: string) {
  return api.post(`/interview/${sessionId}/answer`, {
    question_id: questionId,
    answer_text: answerText,
  })
}

export async function endInterview(sessionId: string) {
  return api.post(`/interview/${sessionId}/end`)
}

export async function getQuestions(sessionId: string) {
  return api.get(`/interview/${sessionId}/questions`)
}

// --- Report ---
export async function getReport(sessionId: string) {
  return api.get(`/interview/${sessionId}/report`)
}

export async function getInterviewHistory() {
  return api.get('/interview/history')
}

export function getStreamUrl(sessionId: string): string {
  return `/api/v1/interview/${sessionId}/stream`
}

// --- Health ---
export async function healthCheck() {
  return api.get('/health')
}

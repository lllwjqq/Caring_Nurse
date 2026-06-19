import axios from 'axios'

const API_URL = import.meta.env.VITE_API_URL || ''

const api = axios.create({
  baseURL: `${API_URL}/api`,
  headers: { 'Content-Type': 'application/json' },
})

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

api.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.status === 401) {
      localStorage.removeItem('access_token')
      localStorage.removeItem('refresh_token')
      window.location.href = '/login'
    }
    return Promise.reject(err)
  }
)

export const authApi = {
  register: (data: { email: string; password: string; full_name: string; agreed_disclaimer: boolean }) =>
    api.post('/auth/register', data),
  login: (data: { email: string; password: string }) => api.post('/auth/login', data),
  me: () => api.get('/auth/me'),
}

export const patientApi = {
  getProfile: () => api.get('/patients/me'),
  updateProfile: (data: Record<string, unknown>) => api.put('/patients/me', data),
  setupProfile: (data: Record<string, unknown>) => api.post('/patients/me/setup', data),
}

export const healthApi = {
  getDashboard: () => api.get('/health/dashboard'),
  createRecord: (data: Record<string, unknown>) => api.post('/health/records', data),
  listRecords: (params?: Record<string, unknown>) => api.get('/health/records', { params }),
  createLifestyle: (data: Record<string, unknown>) => api.post('/health/lifestyle', data),
  listLifestyle: () => api.get('/health/lifestyle'),
}

export const featureApi = {
  listAlerts: (unresolved_only = false) => api.get('/alerts', { params: { unresolved_only } }),
  markAlertRead: (id: number) => api.patch(`/alerts/${id}/read`),
  resolveAlert: (id: number) => api.patch(`/alerts/${id}/resolve`),
  listCarePlans: () => api.get('/care-plans'),
  listFollowups: () => api.get('/follow-ups'),
  submitFollowup: (id: number, responses: Record<string, unknown>) =>
    api.post(`/follow-ups/${id}/submit`, { responses }),
  uploadDocument: (file: File) => {
    const form = new FormData()
    form.append('file', file)
    return api.post('/documents/upload', form, { headers: { 'Content-Type': 'multipart/form-data' } })
  },
  listDocuments: () => api.get('/documents'),
}

export const agentApi = {
  chat: (message: string, session_id?: string) =>
    api.post('/agents/chat', { message, session_id }),
  getTraces: (session_id: string) => api.get(`/agents/traces/${session_id}`),
}

export const knowledgeApi = {
  getGraph: () => api.get('/knowledge/graph'),
}

export default api

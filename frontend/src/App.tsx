import { Navigate, Route, Routes } from 'react-router-dom'
import Layout from './components/Layout'
import LoginPage from './pages/LoginPage'
import RegisterPage from './pages/RegisterPage'
import DashboardPage from './pages/DashboardPage'
import RecordsPage from './pages/RecordsPage'
import ChatPage from './pages/ChatPage'
import AlertsPage from './pages/AlertsPage'
import PlansPage from './pages/PlansPage'
import FollowupPage from './pages/FollowupPage'
import DocumentsPage from './pages/DocumentsPage'
import KnowledgePage from './pages/KnowledgePage'
import ProfilePage from './pages/ProfilePage'
import SetupPage from './pages/SetupPage'

function PrivateRoute({ children }: { children: React.ReactNode }) {
  const token = localStorage.getItem('access_token')
  return token ? <>{children}</> : <Navigate to="/login" replace />
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />
      <Route path="/setup" element={<PrivateRoute><SetupPage /></PrivateRoute>} />
      <Route element={<PrivateRoute><Layout /></PrivateRoute>}>
        <Route path="/" element={<DashboardPage />} />
        <Route path="/records" element={<RecordsPage />} />
        <Route path="/chat" element={<ChatPage />} />
        <Route path="/alerts" element={<AlertsPage />} />
        <Route path="/plans" element={<PlansPage />} />
        <Route path="/followups" element={<FollowupPage />} />
        <Route path="/documents" element={<DocumentsPage />} />
        <Route path="/knowledge" element={<KnowledgePage />} />
        <Route path="/profile" element={<ProfilePage />} />
      </Route>
    </Routes>
  )
}

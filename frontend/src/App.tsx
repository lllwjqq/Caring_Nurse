import type { ReactNode } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import Layout from './components/Layout'
import { ToastProvider } from './components/Toast'
import { AlertProvider } from './context/AlertContext'
import { SettingsProvider } from './context/SettingsContext'
import { VoiceProvider } from './context/VoiceContext'
import ChatPage from './pages/ChatPage'
import DocumentConfirmPage from './pages/DocumentConfirmPage'
import LoginPage from './pages/LoginPage'
import MedicationPage from './pages/MedicationPage'
import MonitorPage from './pages/MonitorPage'
import ProfilePage from './pages/ProfilePage'
import RecordPage from './pages/RecordPage'
import RegisterPage from './pages/RegisterPage'
import SetupPage from './pages/SetupPage'
import AlertHistoryPage from './pages/SubPages/AlertHistoryPage'
import CarePlansPage from './pages/SubPages/CarePlansPage'
import HealthProfilePage from './pages/SubPages/HealthProfilePage'
import LegalPage from './pages/SubPages/LegalPage'
import SettingsPage from './pages/SubPages/SettingsPage'

function PrivateRoute({ children }: { children: ReactNode }) {
  const token = localStorage.getItem('access_token')
  return token ? <>{children}</> : <Navigate to="/login" replace />
}

function Providers({ children }: { children: ReactNode }) {
  return (
    <SettingsProvider>
      <VoiceProvider>
        <AlertProvider>
          <ToastProvider>{children}</ToastProvider>
        </AlertProvider>
      </VoiceProvider>
    </SettingsProvider>
  )
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />
      <Route
        path="/setup"
        element={
          <PrivateRoute>
            <SetupPage />
          </PrivateRoute>
        }
      />

      <Route
        element={
          <PrivateRoute>
            <Providers>
              <Layout />
            </Providers>
          </PrivateRoute>
        }
      >
        <Route path="/" element={<ChatPage />} />
        <Route path="/monitor" element={<MonitorPage />} />
        <Route path="/record" element={<RecordPage />} />
        <Route path="/record/document/:id" element={<DocumentConfirmPage />} />
        <Route path="/medication" element={<MedicationPage />} />
        <Route path="/me" element={<ProfilePage />} />
        <Route path="/me/profile" element={<HealthProfilePage />} />
        <Route path="/me/plans" element={<CarePlansPage />} />
        <Route path="/me/alerts" element={<AlertHistoryPage />} />
        <Route path="/me/settings" element={<SettingsPage />} />
        <Route path="/me/settings/legal/:doc" element={<LegalPage />} />
      </Route>
    </Routes>
  )
}

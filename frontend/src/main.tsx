import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import App from './App'
import { applySettings, loadSettings } from './lib/settings'
import './index.css'

// 渲染前先应用字号/对比设置，避免首屏闪烁（规格 §3.2）
applySettings(loadSettings())

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </React.StrictMode>,
)

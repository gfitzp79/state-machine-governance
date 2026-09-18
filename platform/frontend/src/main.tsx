import React from 'react'
import ReactDOM from 'react-dom/client'
import { HashRouter, Navigate, Outlet, Route, Routes } from 'react-router-dom'
import './index.css'
import Layout from './components/Layout'
import { ToastProvider } from './components/ui'
import { getToken } from './lib/api'

import Login from './pages/Login'
import Dashboard from './pages/Dashboard'
import Risks from './pages/Risks'
import RiskDetail from './pages/RiskDetail'
import Compliance from './pages/Compliance'
import Controls from './pages/Controls'
import ControlDetail from './pages/ControlDetail'
import Policies from './pages/Policies'
import PolicyDetail from './pages/PolicyDetail'
import Treatments from './pages/Treatments'
import TreatmentDetail from './pages/TreatmentDetail'
import ThreatModels from './pages/ThreatModels'
import ThreatModelDetail from './pages/ThreatModelDetail'
import Engine from './pages/Engine'
import Audit from './pages/Audit'
import Notifications from './pages/Notifications'

function RequireAuth() {
  return getToken() ? <Outlet /> : <Navigate to="/login" replace />
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <ToastProvider>
      <HashRouter>
        <Routes>
          <Route path="/login" element={<Login />} />
          <Route element={<RequireAuth />}>
            <Route element={<Layout />}>
              <Route index element={<Dashboard />} />
              <Route path="risks" element={<Risks />} />
              <Route path="risks/:id" element={<RiskDetail />} />
              <Route path="controls" element={<Controls />} />
              <Route path="controls/:id" element={<ControlDetail />} />
              <Route path="policies" element={<Policies />} />
              <Route path="policies/:id" element={<PolicyDetail />} />
              <Route path="treatments" element={<Treatments />} />
              <Route path="treatments/:id" element={<TreatmentDetail />} />
              <Route path="threat-models" element={<ThreatModels />} />
              <Route path="threat-models/:id" element={<ThreatModelDetail />} />
              <Route path="compliance" element={<Compliance />} />
              <Route path="engine" element={<Engine />} />
              <Route path="audit" element={<Audit />} />
              <Route path="notifications" element={<Notifications />} />
            </Route>
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </HashRouter>
    </ToastProvider>
  </React.StrictMode>,
)

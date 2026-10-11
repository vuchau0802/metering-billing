import { useState } from 'react'
import { LogOut, ShieldCheck } from 'lucide-react'

import { getAccount } from './api/client'
import type { TenantCredentials } from './api/types'
import {
  clearTenantCredentials,
  loadTenantCredentials,
  saveTenantCredentials,
} from './auth/session'
import { ConnectPage } from './pages/ConnectPage'
import { DashboardPage } from './pages/DashboardPage'
import { Navigate, Route, Routes } from 'react-router-dom'
import { InvoicePage } from './pages/InvoicePage'
import { BillingResultPage } from './pages/BillingResultPage'

function App() {
  const [credentials, setCredentials] =
    useState<TenantCredentials | null>(
      loadTenantCredentials,
    )

  async function handleConnect(
    nextCredentials: TenantCredentials,
  ): Promise<void> {
    await getAccount(nextCredentials)
    saveTenantCredentials(nextCredentials)
    setCredentials(nextCredentials)
  }

  function handleDisconnect(): void {
    clearTenantCredentials()
    setCredentials(null)
  }

  if (credentials === null) {
    return <ConnectPage onConnect={handleConnect} />
  }

  return (
    <main className="dashboard-page">
      <header className="app-header">
        <div className="app-brand">
          <span className="brand-mark" aria-hidden="true">
            <ShieldCheck size={20} />
          </span>
          <span>Usage Billing</span>
        </div>

        <button
          className="secondary-button"
          type="button"
          onClick={handleDisconnect}
        >
          <LogOut size={17} aria-hidden="true" />
          Disconnect
        </button>
      </header>

      <Routes>
        <Route
          path="/billing/success"
          element={<BillingResultPage result="success" />}
        />
        <Route
          path="/billing/cancel"
          element={<BillingResultPage result="canceled" />}
        />
        <Route
          path="/"
          element={<DashboardPage credentials={credentials} />}
        />
        <Route
          path="/invoices/:invoiceId"
          element={<InvoicePage credentials={credentials} />}
        />
        <Route path="*" element={<Navigate replace to="/" />} />
      </Routes>
    </main>
  )
}

export default App

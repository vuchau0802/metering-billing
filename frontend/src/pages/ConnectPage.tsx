import { useState } from 'react'
import type { FormEvent } from 'react'
import {
  ArrowRight,
  KeyRound,
  LoaderCircle,
  ShieldCheck,
} from 'lucide-react'

import { ApiError } from '../api/client'
import type { TenantCredentials } from '../api/types'

interface ConnectPageProps {
  onConnect: (credentials: TenantCredentials) => Promise<void>
}

export function ConnectPage({
  onConnect,
}: ConnectPageProps) {
  const [tenantId, setTenantId] = useState('')
  const [apiKey, setApiKey] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [isConnecting, setIsConnecting] = useState(false)

  async function handleSubmit(
    event: FormEvent<HTMLFormElement>,
  ) {
    event.preventDefault()
    setError(null)

    const parsedTenantId = Number(tenantId)

    if (!Number.isInteger(parsedTenantId) || parsedTenantId <= 0) {
      setError('Enter a valid tenant ID.')
      return
    }

    if (apiKey.trim().length === 0) {
      setError('Enter your tenant API key.')
      return
    }

    setIsConnecting(true)

    try {
      await onConnect({
        tenantId: parsedTenantId,
        apiKey: apiKey.trim(),
      })
    } catch (requestError) {
      setError(
        requestError instanceof ApiError
          ? requestError.message
          : 'Unable to connect to the billing service.',
      )
    } finally {
      setIsConnecting(false)
    }
  }

  return (
    <main className="connect-page">
      <section className="connect-panel">
        <div className="brand-mark" aria-hidden="true">
          <ShieldCheck size={24} strokeWidth={2} />
        </div>

        <div className="connect-heading">
          <p className="eyebrow">Usage Billing</p>
          <h1>Billing console</h1>
          <p>Connect with your tenant credentials.</p>
        </div>

        <form className="connect-form" noValidate onSubmit={handleSubmit}>
          <label htmlFor="tenant-id">Tenant ID</label>
          <input
            id="tenant-id"
            inputMode="numeric"
            min="1"
            name="tenant-id"
            placeholder="1"
            required
            type="number"
            value={tenantId}
            onChange={(event) => setTenantId(event.target.value)}
          />

          <label htmlFor="tenant-key">Tenant API key</label>
          <div className="input-with-icon">
            <KeyRound size={18} aria-hidden="true" />
            <input
              autoComplete="current-password"
              id="tenant-key"
              name="tenant-key"
              placeholder="Enter API key"
              required
              type="password"
              value={apiKey}
              onChange={(event) => setApiKey(event.target.value)}
            />
          </div>

          {error !== null && (
            <p className="form-error" role="alert">
              {error}
            </p>
          )}

          <button
            className="primary-button"
            disabled={isConnecting}
            type="submit"
          >
            {isConnecting ? (
              <LoaderCircle
                className="spin"
                size={18}
                aria-hidden="true"
              />
            ) : (
              <ArrowRight size={18} aria-hidden="true" />
            )}
            {isConnecting ? 'Connecting' : 'Continue'}
          </button>
        </form>

        <p className="privacy-note">
          Credentials remain in this browser tab.
        </p>
      </section>
    </main>
  )
}
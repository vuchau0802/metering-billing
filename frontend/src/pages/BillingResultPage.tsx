import { useEffect } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import {
  ArrowRight,
  CheckCircle2,
  XCircle,
} from 'lucide-react'
import { Link, useSearchParams } from 'react-router-dom'

interface BillingResultPageProps {
  result: 'success' | 'canceled'
}

export function BillingResultPage({
  result,
}: BillingResultPageProps) {
  const queryClient = useQueryClient()
  const [searchParams] = useSearchParams()
  const sessionId = searchParams.get('session_id')
  const isSuccess = result === 'success'

  useEffect(() => {
    if (isSuccess) {
      void queryClient.invalidateQueries()
    }
  }, [isSuccess, queryClient])

  return (
    <main className="result-page">
      <section className="result-panel">
        <span
          className={`result-icon ${
            isSuccess ? 'result-success' : 'result-canceled'
          }`}
          aria-hidden="true"
        >
          {isSuccess ? (
            <CheckCircle2 size={30} />
          ) : (
            <XCircle size={30} />
          )}
        </span>

        <p className="eyebrow">Stripe Checkout</p>

        <h1>
          {isSuccess
            ? 'Upgrade completed'
            : 'Checkout canceled'}
        </h1>

        <p>
          {isSuccess
            ? 'Your subscription is being synchronized from Stripe.'
            : 'No subscription changes were made.'}
        </p>

        {isSuccess && sessionId && (
          <div className="session-reference">
            <span>Session reference</span>
            <code>{sessionId}</code>
          </div>
        )}

        <Link className="primary-button result-action" to="/">
          View billing dashboard
          <ArrowRight size={18} />
        </Link>
      </section>
    </main>
  )
}
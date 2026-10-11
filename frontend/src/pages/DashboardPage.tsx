import { useMutation, useQuery } from '@tanstack/react-query'
import {
  Activity,
  Bot,
  CalendarDays,
  CircleDollarSign,
  CreditCard,
  ExternalLink,
  RefreshCw,
  TrendingUp,
} from 'lucide-react'
import type { ReactNode } from 'react'

import {
  createCheckout,
  getAccount,
  getInvoices,
  getUsage,
} from '../api/client'
import type {
  QuotaUsage,
  TenantCredentials,
} from '../api/types'
import {
  formatDate,
  formatMicrousd,
  formatNumber,
  formatPlan,
  formatStatus,
} from '../lib/format'
import { Link } from 'react-router-dom'

interface DashboardPageProps {
  credentials: TenantCredentials
}

interface QuotaPanelProps {
  icon: ReactNode
  label: string
  quota: QuotaUsage
}

function QuotaPanel({
  icon,
  label,
  quota,
}: QuotaPanelProps) {
  const percentage =
    quota.limit === 0
      ? 0
      : Math.min(100, Math.round((quota.used / quota.limit) * 100))

  return (
    <article className="quota-panel">
      <div className="quota-heading">
        <span className="quota-icon">{icon}</span>
        <div>
          <h3>{label}</h3>
          <p>{percentage}% of included usage</p>
        </div>
      </div>

      <div
        className="quota-meter"
        role="progressbar"
        aria-label={`${label} usage`}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={percentage}
      >
        <span style={{ width: `${percentage}%` }} />
      </div>

      <div className="quota-values">
        <strong>{formatNumber(quota.used)} used</strong>
        <span>{formatNumber(quota.limit)} included</span>
      </div>

      {quota.overage > 0 && (
        <p className="overage-note">
          {formatNumber(quota.overage)} units in overage
        </p>
      )}
    </article>
  )
}

function getErrorMessage(error: unknown): string {
  return error instanceof Error
    ? error.message
    : 'Unable to load billing data.'
}

export function DashboardPage({
  credentials,
}: DashboardPageProps) {
  const accountQuery = useQuery({
    queryKey: ['account', credentials.tenantId],
    queryFn: () => getAccount(credentials),
  })

  const usageQuery = useQuery({
    queryKey: ['usage', credentials.tenantId],
    queryFn: () => getUsage(credentials),
  })

  const invoicesQuery = useQuery({
    queryKey: ['invoices', credentials.tenantId],
    queryFn: () => getInvoices(credentials),
  })

  const checkoutMutation = useMutation({
    mutationFn: () => createCheckout(credentials),
    onSuccess: (checkout) => {
      window.location.assign(checkout.checkout_url)
    },
  })

  const isLoading =
    accountQuery.isPending ||
    usageQuery.isPending ||
    invoicesQuery.isPending

  const error =
    accountQuery.error ??
    usageQuery.error ??
    invoicesQuery.error

  async function refreshDashboard(): Promise<void> {
    await Promise.all([
      accountQuery.refetch(),
      usageQuery.refetch(),
      invoicesQuery.refetch(),
    ])
  }

  if (isLoading) {
    return (
      <section className="dashboard-state" aria-live="polite">
        <RefreshCw className="spin" size={22} />
        <p>Loading billing data</p>
      </section>
    )
  }

  if (error !== null) {
    return (
      <section className="dashboard-state error-state" role="alert">
        <h1>Billing data unavailable</h1>
        <p>{getErrorMessage(error)}</p>
        <button
          className="secondary-button"
          type="button"
          onClick={() => void refreshDashboard()}
        >
          <RefreshCw size={17} />
          Try again
        </button>
      </section>
    )
  }

  const account = accountQuery.data
  const usage = usageQuery.data
  const invoices = invoicesQuery.data

  if (!account || !usage || !invoices) {
    return null
  }

  const billingPeriodEnd =
    account.subscription?.current_period_end ?? usage.window.end

  return (
    <div className="dashboard-content">
      <section className="account-band">
        <div>
          <p className="eyebrow">Tenant {account.tenant_id}</p>
          <h1>{account.email ?? 'Billing account'}</h1>
          <div className="account-status">
            <span className={`plan-badge plan-${account.plan}`}>
              {formatPlan(account.plan)}
            </span>
            <span className={`status-badge status-${account.status}`}>
              {formatStatus(account.status)}
            </span>
            <span className="period-label">
              <CalendarDays size={15} />
              Renews {formatDate(billingPeriodEnd)}
            </span>
          </div>
        </div>

        <div className="account-actions">
          <button
            className="icon-button"
            title="Refresh billing data"
            type="button"
            onClick={() => void refreshDashboard()}
          >
            <RefreshCw size={18} />
          </button>

          {account.plan === 'free' && (
            <button
              className="primary-button upgrade-button"
              disabled={checkoutMutation.isPending}
              type="button"
              onClick={() => checkoutMutation.mutate()}
            >
              <CreditCard size={18} />
              {checkoutMutation.isPending
                ? 'Opening Checkout'
                : 'Upgrade to Pro'}
            </button>
          )}
        </div>
      </section>

      {checkoutMutation.error && (
        <p className="form-error" role="alert">
          {getErrorMessage(checkoutMutation.error)}
        </p>
      )}

      <section className="metric-strip" aria-label="Billing totals">
        <article>
          <span className="metric-icon">
            <CircleDollarSign size={19} />
          </span>
          <p>Current usage</p>
          <strong>{formatMicrousd(usage.cost_microusd)}</strong>
        </article>

        <article>
          <span className="metric-icon">
            <TrendingUp size={19} />
          </span>
          <p>Projected month</p>
          <strong>
            {formatMicrousd(usage.projected_cost_microusd)}
          </strong>
        </article>

        <article>
          <span className="metric-icon">
            <Activity size={19} />
          </span>
          <p>Overage charges</p>
          <strong>
            {formatMicrousd(usage.overage_cost_microusd)}
          </strong>
        </article>

        <article>
          <span className="metric-icon">
            <CreditCard size={19} />
          </span>
          <p>Finalized invoices</p>
          <strong>{formatNumber(invoices.length)}</strong>
        </article>
      </section>

      <section className="content-section">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Current period</p>
            <h2>Usage and quotas</h2>
          </div>
          <p>
            {formatDate(usage.window.start)} –{' '}
            {formatDate(usage.window.end)}
          </p>
        </div>

        <div className="quota-grid">
          <QuotaPanel
            icon={<Activity size={19} />}
            label="API calls"
            quota={usage.usage.api_calls}
          />
          <QuotaPanel
            icon={<Bot size={19} />}
            label="AI tokens"
            quota={usage.usage.ai_tokens}
          />
        </div>
      </section>

      <section className="content-section">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Statements</p>
            <h2>Recent invoices</h2>
          </div>
        </div>

        {invoices.length === 0 ? (
          <div className="empty-state">
            <CreditCard size={22} />
            <p>No finalized invoices yet.</p>
          </div>
        ) : (
          <div className="invoice-table-wrap">
            <table className="invoice-table">
              <thead>
                <tr>
                  <th>Invoice</th>
                  <th>Period</th>
                  <th>Status</th>
                  <th>Total</th>
                  <th aria-label="Open invoice" />
                </tr>
              </thead>
              <tbody>
                {invoices.slice(0, 5).map((invoice) => (
                  <tr key={invoice.id}>
                    <td>INV-{String(invoice.id).padStart(5, '0')}</td>
                    <td>
                      {formatDate(invoice.period_start)} –{' '}
                      {formatDate(invoice.period_end)}
                    </td>
                    <td>
                      <span className="status-badge status-active">
                        {formatStatus(invoice.status)}
                      </span>
                    </td>
                    <td>{formatMicrousd(invoice.total_microusd)}</td>
                    <td>
                      <Link
                        className="table-action"
                        title={`Open invoice ${invoice.id}`}
                        aria-label={`Open invoice ${invoice.id}`}
                        to={`/invoices/${invoice.id}`}
                      >
                        <ExternalLink size={16} />
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  )
}
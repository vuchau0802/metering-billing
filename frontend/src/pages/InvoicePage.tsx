import { useQuery } from '@tanstack/react-query'
import {
  ArrowLeft,
  FileText,
  RefreshCw,
} from 'lucide-react'
import { Link, useParams } from 'react-router-dom'

import { getInvoice } from '../api/client'
import type { TenantCredentials } from '../api/types'
import {
  formatDate,
  formatMicrousd,
  formatNumber,
  formatPlan,
  formatStatus,
} from '../lib/format'

interface InvoicePageProps {
  credentials: TenantCredentials
}

export function InvoicePage({
  credentials,
}: InvoicePageProps) {
  const { invoiceId } = useParams()
  const parsedInvoiceId = Number(invoiceId)
  const isValidInvoiceId =
    Number.isInteger(parsedInvoiceId) && parsedInvoiceId > 0

  const invoiceQuery = useQuery({
    queryKey: [
      'invoice',
      credentials.tenantId,
      parsedInvoiceId,
    ],
    queryFn: () => getInvoice(credentials, parsedInvoiceId),
    enabled: isValidInvoiceId,
  })

  if (!isValidInvoiceId) {
    return (
      <section className="dashboard-state error-state">
        <h1>Invalid invoice</h1>
        <Link className="secondary-button text-link" to="/">
          <ArrowLeft size={17} />
          Return to dashboard
        </Link>
      </section>
    )
  }

  if (invoiceQuery.isPending) {
    return (
      <section className="dashboard-state" aria-live="polite">
        <RefreshCw className="spin" size={22} />
        <p>Loading invoice</p>
      </section>
    )
  }

  if (invoiceQuery.error || !invoiceQuery.data) {
    return (
      <section className="dashboard-state error-state">
        <h1>Invoice unavailable</h1>
        <p>
          {invoiceQuery.error instanceof Error
            ? invoiceQuery.error.message
            : 'The invoice could not be loaded.'}
        </p>
        <Link className="secondary-button text-link" to="/">
          <ArrowLeft size={17} />
          Return to dashboard
        </Link>
      </section>
    )
  }

  const invoice = invoiceQuery.data

  return (
    <div className="dashboard-content invoice-page">
      <Link className="back-link" to="/">
        <ArrowLeft size={17} />
        Back to dashboard
      </Link>

      <section className="invoice-heading">
        <div>
          <p className="eyebrow">Finalized statement</p>
          <h1>
            INV-{String(invoice.id).padStart(5, '0')}
          </h1>
          <p>
            {formatDate(invoice.period_start)} –{' '}
            {formatDate(invoice.period_end)}
          </p>
        </div>

        <div className="invoice-total">
          <span>{formatStatus(invoice.status)}</span>
          <strong>{formatMicrousd(invoice.total_microusd)}</strong>
          <small>{invoice.currency.toUpperCase()}</small>
        </div>
      </section>

      <section className="invoice-summary">
        <article>
          <p>Usage subtotal</p>
          <strong>
            {formatMicrousd(invoice.subtotal_microusd)}
          </strong>
        </article>
        <article>
          <p>Overage charges</p>
          <strong>
            {formatMicrousd(invoice.overage_cost_microusd)}
          </strong>
        </article>
        <article>
          <p>Plan adjustments</p>
          <strong>
            {formatMicrousd(invoice.adjustment_microusd)}
          </strong>
        </article>
        <article>
          <p>Generated</p>
          <strong>{formatDate(invoice.generated_at)}</strong>
        </article>
      </section>

      <section className="content-section">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Metered activity</p>
            <h2>Usage line items</h2>
          </div>
        </div>

        {invoice.lines.length === 0 ? (
          <div className="empty-state">
            <FileText size={22} />
            <p>No usage was recorded for this period.</p>
          </div>
        ) : (
          <div className="invoice-table-wrap">
            <table className="invoice-table">
              <thead>
                <tr>
                  <th>Description</th>
                  <th>Events</th>
                  <th>Quantity</th>
                  <th>Overage</th>
                  <th>Total</th>
                </tr>
              </thead>
              <tbody>
                {invoice.lines.map((line) => (
                  <tr key={line.usage_type}>
                    <td>{line.description}</td>
                    <td>{formatNumber(line.event_count)}</td>
                    <td>{formatNumber(line.quantity)}</td>
                    <td>
                      {formatNumber(line.overage_quantity)}
                    </td>
                    <td>
                      {formatMicrousd(line.total_microusd)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {invoice.adjustments.length > 0 && (
        <section className="content-section">
          <div className="section-heading">
            <div>
              <p className="eyebrow">Plan changes</p>
              <h2>Billing adjustments</h2>
            </div>
          </div>

          <div className="adjustment-list">
            {invoice.adjustments.map((adjustment) => (
              <article key={adjustment.id}>
                <div>
                  <strong>
                    {formatPlan(adjustment.old_plan)} to{' '}
                    {formatPlan(adjustment.new_plan)}
                  </strong>
                  <p>
                    Effective {formatDate(adjustment.effective_at)}
                  </p>
                </div>
                <strong>
                  {formatMicrousd(adjustment.amount_microusd)}
                </strong>
              </article>
            ))}
          </div>
        </section>
      )}
    </div>
  )
}
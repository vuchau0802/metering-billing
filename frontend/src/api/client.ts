import type {
  AccountResponse,
  ApiErrorResponse,
  CheckoutResponse,
  InvoiceDetail,
  InvoiceSummary,
  TenantCredentials,
  UsageResponse,
} from './types'

export class ApiError extends Error {
  readonly status: number
  readonly code: string

  constructor(message: string, status: number, code = 'request_failed') {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
  }
}

async function apiRequest<T>(
  path: string,
  apiKey: string,
  options: RequestInit = {},
): Promise<T> {
  const headers = new Headers(options.headers)
  headers.set('X-Tenant-Key', apiKey)

  if (options.body !== undefined) {
    headers.set('Content-Type', 'application/json')
  }

  const response = await fetch(`/api${path}`, {
    ...options,
    headers,
  })

  if (!response.ok) {
    const payload = (await response.json().catch(() => null)) as
      | ApiErrorResponse
      | null

    throw new ApiError(
      payload?.error.message ?? 'The request could not be completed.',
      response.status,
      payload?.error.code,
    )
  }

  return (await response.json()) as T
}

export function getAccount({
  tenantId,
  apiKey,
}: TenantCredentials): Promise<AccountResponse> {
  return apiRequest<AccountResponse>(
    `/account/${tenantId}`,
    apiKey,
  )
}

export function getUsage({
  tenantId,
  apiKey,
}: TenantCredentials): Promise<UsageResponse> {
  return apiRequest<UsageResponse>(
    `/usage/${tenantId}`,
    apiKey,
  )
}

export function getInvoices({
  tenantId,
  apiKey,
}: TenantCredentials): Promise<InvoiceSummary[]> {
  return apiRequest<InvoiceSummary[]>(
    `/invoices/${tenantId}`,
    apiKey,
  )
}

export function getInvoice(
  credentials: TenantCredentials,
  invoiceId: number,
): Promise<InvoiceDetail> {
  return apiRequest<InvoiceDetail>(
    `/invoices/${credentials.tenantId}/${invoiceId}`,
    credentials.apiKey,
  )
}

export function createCheckout({
  tenantId,
  apiKey,
}: TenantCredentials): Promise<CheckoutResponse> {
  return apiRequest<CheckoutResponse>(
    '/billing/checkout',
    apiKey,
    {
      method: 'POST',
      body: JSON.stringify({ tenant_id: tenantId }),
    },
  )
}
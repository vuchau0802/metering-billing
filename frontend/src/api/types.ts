export type UsageType = 'api_call' | 'ai_tokens'

export interface QuotaUsage {
  used: number
  limit: number
  remaining: number
  overage: number
}

export interface UsageResponse {
  tenant_id: number
  window: {
    start: string
    end: string
  }
  usage: {
    api_calls: QuotaUsage
    ai_tokens: QuotaUsage
  }
  cost_microusd: number
  overage_enabled: boolean
  overage_cost_microusd: number
  projected_cost_microusd: number
}

export interface InvoiceSummary {
  id: number
  tenant_id: number
  period_start: string
  period_end: string
  status: 'finalized'
  currency: 'usd'
  subtotal_microusd: number
  overage_cost_microusd: number
  total_microusd: number
  generated_at: string
}

export interface InvoiceLine {
  usage_type: UsageType
  description: string
  event_count: number
  quantity: number
  overage_quantity: number
  subtotal_microusd: number
  overage_cost_microusd: number
  total_microusd: number
}

export interface InvoiceAdjustment {
  id: number
  source_event_id: string
  old_plan: 'free' | 'pro'
  new_plan: 'free' | 'pro'
  period_start: string
  period_end: string
  effective_at: string
  old_monthly_price_microusd: number
  new_monthly_price_microusd: number
  amount_microusd: number
  currency: 'usd'
}

export interface InvoiceDetail extends InvoiceSummary {
  adjustment_microusd: number
  lines: InvoiceLine[]
  adjustments: InvoiceAdjustment[]
}

export interface CheckoutResponse {
  session_id: string
  checkout_url: string
}

export interface ApiErrorResponse {
  error: {
    code: string
    message: string
  }
}

export interface TenantCredentials {
  tenantId: number
  apiKey: string
}

export type TenantStatus =
  | 'active'
  | 'past_due'
  | 'canceled'
  | 'incomplete'

export type SubscriptionStatus =
  | TenantStatus
  | 'trialing'

export interface AccountSubscription {
  status: SubscriptionStatus
  current_period_start: string | null
  current_period_end: string | null
  cancel_at_period_end: boolean
}

export interface AccountResponse {
  tenant_id: number
  email: string | null
  plan: 'free' | 'pro'
  status: TenantStatus
  subscription: AccountSubscription | null
}
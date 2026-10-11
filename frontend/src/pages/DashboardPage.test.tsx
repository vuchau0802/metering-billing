import {
  QueryClient,
  QueryClientProvider,
} from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import {
  beforeEach,
  describe,
  expect,
  it,
  vi,
} from 'vitest'

import {
  getAccount,
  getInvoices,
  getUsage,
} from '../api/client'
import { DashboardPage } from './DashboardPage'

vi.mock('../api/client', () => ({
  createCheckout: vi.fn(),
  getAccount: vi.fn(),
  getInvoices: vi.fn(),
  getUsage: vi.fn(),
}))

const credentials = {
  tenantId: 1,
  apiKey: 'tenant-test-key',
}

function renderDashboard(): void {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  })

  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <DashboardPage credentials={credentials} />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('DashboardPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()

    vi.mocked(getAccount).mockResolvedValue({
      tenant_id: 1,
      email: 'alice@example.com',
      plan: 'pro',
      status: 'active',
      subscription: {
        status: 'active',
        current_period_start: '2026-10-01T00:00:00Z',
        current_period_end: '2026-11-01T00:00:00Z',
        cancel_at_period_end: false,
      },
    })

    vi.mocked(getUsage).mockResolvedValue({
      tenant_id: 1,
      window: {
        start: '2026-10-01T00:00:00Z',
        end: '2026-11-01T00:00:00Z',
      },
      usage: {
        api_calls: {
          used: 40_000,
          limit: 50_000,
          remaining: 10_000,
          overage: 0,
        },
        ai_tokens: {
          used: 120_000,
          limit: 5_000_000,
          remaining: 4_880_000,
          overage: 0,
        },
      },
      cost_microusd: 12_500_000,
      overage_enabled: true,
      overage_cost_microusd: 0,
      projected_cost_microusd: 20_000_000,
    })

    vi.mocked(getInvoices).mockResolvedValue([
      {
        id: 5,
        tenant_id: 1,
        period_start: '2026-09-01T00:00:00Z',
        period_end: '2026-10-01T00:00:00Z',
        status: 'finalized',
        currency: 'usd',
        subtotal_microusd: 9_000_000,
        overage_cost_microusd: 1_000_000,
        total_microusd: 10_000_000,
        generated_at: '2026-10-02T00:00:00Z',
      },
    ])
  })

  it('renders account, usage, costs, and invoices', async () => {
    renderDashboard()

    expect(
      await screen.findByRole('heading', {
        name: 'alice@example.com',
      }),
    ).toBeInTheDocument()

    expect(screen.getByText('$12.50')).toBeInTheDocument()
    expect(screen.getByText('$20.00')).toBeInTheDocument()

    expect(
      screen.getByRole('progressbar', {
        name: 'API calls usage',
      }),
    ).toHaveAttribute('aria-valuenow', '80')

    expect(
      screen.getByRole('link', {
        name: 'Open invoice 5',
      }),
    ).toHaveAttribute('href', '/invoices/5')
  })
})
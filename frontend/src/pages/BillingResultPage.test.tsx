import {
  QueryClient,
  QueryClientProvider,
} from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'

import { BillingResultPage } from './BillingResultPage'

function renderResultPage(
  result: 'success' | 'canceled',
  route: string,
): void {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  })

  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[route]}>
        <BillingResultPage result={result} />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

describe('BillingResultPage', () => {
  it('shows a successful Checkout result', () => {
    renderResultPage(
      'success',
      '/billing/success?session_id=cs_test_example',
    )

    expect(
      screen.getByRole('heading', {
        name: 'Upgrade completed',
      }),
    ).toBeInTheDocument()

    expect(
      screen.getByText('cs_test_example'),
    ).toBeInTheDocument()

    expect(
      screen.getByRole('link', {
        name: 'View billing dashboard',
      }),
    ).toHaveAttribute('href', '/')
  })

  it('shows a canceled Checkout result', () => {
    renderResultPage(
      'canceled',
      '/billing/cancel',
    )

    expect(
      screen.getByRole('heading', {
        name: 'Checkout canceled',
      }),
    ).toBeInTheDocument()

    expect(
      screen.getByText('No subscription changes were made.'),
    ).toBeInTheDocument()

    expect(
      screen.queryByText('Session reference'),
    ).not.toBeInTheDocument()
  })
})
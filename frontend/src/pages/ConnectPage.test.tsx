import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { ApiError } from '../api/client'
import { ConnectPage } from './ConnectPage'

describe('ConnectPage', () => {
  it('submits normalized tenant credentials', async () => {
    const user = userEvent.setup()
    const onConnect = vi.fn(async () => undefined)

    render(<ConnectPage onConnect={onConnect} />)

    await user.type(
      screen.getByLabelText('Tenant ID'),
      '42',
    )
    await user.type(
      screen.getByLabelText('Tenant API key'),
      '  tenant-test-key  ',
    )
    await user.click(
      screen.getByRole('button', { name: 'Continue' }),
    )

    expect(onConnect).toHaveBeenCalledWith({
      tenantId: 42,
      apiKey: 'tenant-test-key',
    })
  })

  it('rejects an invalid tenant ID', async () => {
    const user = userEvent.setup()
    const onConnect = vi.fn(async () => undefined)

    render(<ConnectPage onConnect={onConnect} />)

    await user.type(
      screen.getByLabelText('Tenant ID'),
      '0',
    )
    await user.type(
      screen.getByLabelText('Tenant API key'),
      'tenant-test-key',
    )
    await user.click(
      screen.getByRole('button', { name: 'Continue' }),
    )

    expect(
      screen.getByRole('alert'),
    ).toHaveTextContent('Enter a valid tenant ID.')
    expect(onConnect).not.toHaveBeenCalled()
  })

  it('shows an API authentication error', async () => {
    const user = userEvent.setup()
    const onConnect = vi.fn().mockRejectedValue(
      new ApiError(
        'The tenant API key is missing or invalid.',
        401,
        'unauthorized',
      ),
    )

    render(<ConnectPage onConnect={onConnect} />)

    await user.type(
      screen.getByLabelText('Tenant ID'),
      '1',
    )
    await user.type(
      screen.getByLabelText('Tenant API key'),
      'wrong-key',
    )
    await user.click(
      screen.getByRole('button', { name: 'Continue' }),
    )

    expect(
      await screen.findByRole('alert'),
    ).toHaveTextContent(
      'The tenant API key is missing or invalid.',
    )
  })
})
import { vi, it, expect, describe } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import React from 'react'
import Search from './Search'

// Mock SpaceSelect to a simple <select>
vi.mock('@/components/SpaceSelect', () => ({
  __esModule: true,
  default: ({ value, onChange }) => (
    <select aria-label="space" value={value} onChange={(e) => onChange(e.target.value)}>
      <option value="public">public</option>
    </select>
  ),
}))

// Spy-able mock for useApi
const apiMock = vi.fn(async (path, qs = '') => {
  if (path === 'user/spaces') return { spaces: ['public'] }

  if (path === 'search') {
    const q = new URLSearchParams(qs.replace(/^\?/, '')).get('q') || ''
    if (q === 'derecho') {
      return {
        results: [
          { id: 'doc-1', title: 'Document 123', score: 0.87, snippet: 'alpha policy' },
        ],
      }
    }
    if (q === 'nohits') return { results: [] }
    return { results: [] }
  }
  return {}
})
vi.mock('@/hooks/useApi', () => ({
  useApi: (...args) => apiMock(...args),
  apiFetch: (...args) => apiMock(...args),
}))

describe('<Search />', () => {
  it('ignores blank queries (no search, no empty-state)', async () => {
    render(<Search />)

    // waits for spaces load + heading
    await waitFor(() => expect(screen.getByText(/Buscar documentos/i)).toBeInTheDocument())
    expect(apiMock).toHaveBeenCalledWith('user/spaces')

    const btn = screen.getByRole('button', { name: /buscar/i })
    await userEvent.click(btn)
    // Only the initial call to user/spaces should exist so far
    expect(apiMock.mock.calls.filter(c => c[0] === 'search').length).toBe(0)
    // Searched flag stayed false, so no empty-state
    expect(screen.queryByText(/No se encontraron resultados\./)).not.toBeInTheDocument()
  })

  it('runs a real search and renders a result', async () => {
    render(<Search />)
    await screen.findByText(/Buscar documentos/)

    const input = screen.getByPlaceholderText(/Ingresa las palabras/i)
    const btn   = screen.getByRole('button', { name: /buscar/i })

    await userEvent.type(input, 'derecho')
    await userEvent.click(btn)
    await screen.findByText(/Document 123/)
    expect(screen.getByText(/Score:/)).toBeInTheDocument()
  })

  it('shows empty state when query has zero hits', async () => {
    render(<Search />)
    await screen.findByText(/Buscar documentos/)

    const input = screen.getByPlaceholderText(/Ingresa las palabras/i)
    const btn   = screen.getByRole('button', { name: /buscar/i })

    await userEvent.type(input, 'nohits')
    await userEvent.click(btn)

    await screen.findByText(/No se encontraron resultados\./)
  })
})


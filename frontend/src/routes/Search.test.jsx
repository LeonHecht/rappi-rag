import { vi, it, expect } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import React from 'react';
import Search from './Search';

// Mock SpaceSelect to a lightweight placeholder that just renders current value
vi.mock('@/components/SpaceSelect', () => ({
  default: ({ value }) => <div>Space: {value || '(none)'}</div>,
}));

// Mock useApi to return spaces and search results deterministically
const apiMock = vi.fn(async (path) => {
  if (path === 'user/spaces') {
    return { spaces: ['public', 'org1/space-a'] };
  }
  if (path === 'search') {
    return {
      results: [
        { id: '1', title: 'Document One', snippet: 'alpha beta gamma', score: 0.987, download_url: '' },
        { id: '2', title: 'Document Two', snippet: 'delta epsilon', score: 0.765, download_url: '' },
      ],
    };
  }
  return {};
});
vi.mock('@/hooks/useApi', () => ({
  useApi: (...args) => apiMock(...args),
  apiFetch: (...args) => apiMock(...args),
}));

it('loads spaces, performs search, and renders results', async () => {
  render(<Search />);

  // After mount, spaces should be loaded and first selected
  await waitFor(() => expect(screen.getByText('Space: public')).toBeInTheDocument());

  // Type a query and trigger search
  const input = screen.getByPlaceholderText(/Ingresa las palabras/i);
  await userEvent.type(input, 'handbook');
  const button = screen.getByRole('button', { name: 'Buscar' });
  await userEvent.click(button);

  // Results render
  await screen.findByText('Document One');
  expect(screen.getByText('Document Two')).toBeInTheDocument();

  // Ensure useApi called for spaces and search
  expect(apiMock).toHaveBeenCalledWith('user/spaces');
  expect(apiMock).toHaveBeenCalledWith('search', expect.stringMatching(/\?q=handbook/));
});


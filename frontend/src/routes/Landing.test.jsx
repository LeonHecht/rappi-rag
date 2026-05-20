import { vi, beforeEach, test, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import React from 'react';

// Mock motion.div to a plain div to avoid animation timing complexities
vi.mock('framer-motion', () => ({
  motion: { div: ({ children, ...props }) => <div {...props}>{children}</div> },
}));

// Utility to mock useAuth with different user shapes
function mockAuth(session) {
  vi.doMock('../context/AuthContext', () => ({
    useAuth: () => ({ session }),
  }));
}

beforeEach(() => {
  vi.resetModules();
});

test('guest sees product name', async () => {
  mockAuth(null);
  const { default: LandingCmp } = await import('./Landing');
  render(
    <MemoryRouter>
      <LandingCmp />
    </MemoryRouter>
  );
  expect(screen.getByText(/Agentic RAG Template/i)).toBeInTheDocument();
});

test('user with full_name sees "Hola, First"', async () => {
  mockAuth({ user: { user_metadata: { full_name: 'Ada Lovelace' } } });
  const { default: LandingCmp } = await import('./Landing');
  render(
    <MemoryRouter>
      <LandingCmp />
    </MemoryRouter>
  );
  expect(screen.getByText(/Hola, Ada/i)).toBeInTheDocument();
});

test('user with first_name prioritized', async () => {
  mockAuth({ user: { user_metadata: { full_name: 'Grace Hopper', first_name: 'Grace' } } });
  const { default: LandingCmp } = await import('./Landing');
  render(
    <MemoryRouter>
      <LandingCmp />
    </MemoryRouter>
  );
  expect(screen.getByText(/Hola, Grace/i)).toBeInTheDocument();
});

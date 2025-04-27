// Learn more: https://github.com/testing-library/jest-dom
import '@testing-library/jest-dom';

// Mock for Next.js router
jest.mock('next/router', () => ({
  useRouter: () => ({
    push: jest.fn(),
    replace: jest.fn(),
    prefetch: jest.fn(),
    back: jest.fn(),
    pathname: '/',
    query: {},
  }),
}));

// Mock for environment variables if needed
process.env = {
  ...process.env,
  NEXT_PUBLIC_API_URL: 'http://localhost:8000',
}; 
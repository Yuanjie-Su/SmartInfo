import React from 'react';
import { render, screen } from '@testing-library/react';
import { ConfigProvider } from 'antd';
import NewsPage from '../pages/index';

// Mock the newsService
jest.mock('../services/newsService', () => ({
  getCategories: jest.fn().mockResolvedValue([]),
  getSources: jest.fn().mockResolvedValue([]),
  getNews: jest.fn().mockResolvedValue([]),
  fetchNews: jest.fn().mockResolvedValue({ task_id: '123' }),
  analyzeNews: jest.fn().mockResolvedValue({ task_id: '123' }),
  deleteNews: jest.fn().mockResolvedValue({}),
}));

describe('NewsPage', () => {
  it('renders the news page with title', async () => {
    render(
      <ConfigProvider>
        <NewsPage />
      </ConfigProvider>
    );
    
    // Check if the page title is rendered
    expect(await screen.findByText(/News Management/i)).toBeInTheDocument();
  });
}); 
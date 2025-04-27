import React from 'react';
import type { AppProps } from 'next/app';
import { ConfigProvider } from 'antd';
import MainLayout from '@/components/layout/MainLayout';
import '@/styles/globals.css';

export default function App({ Component, pageProps }: AppProps) {
  return (
    <ConfigProvider
      theme={{
        token: {
          colorPrimary: '#1677ff',
        },
      }}
    >
      <MainLayout>
        <Component {...pageProps} />
      </MainLayout>
    </ConfigProvider>
  );
}
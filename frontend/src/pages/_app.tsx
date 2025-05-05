import React from 'react';
import type { AppProps } from 'next/app';
import { ConfigProvider } from 'antd';
import MainLayout from '@/components/layout/MainLayout';
import { AuthProvider } from '@/context/AuthContext'; // Import AuthProvider
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
      <AuthProvider> {/* Wrap MainLayout with AuthProvider */}
        <MainLayout>
          <Component {...pageProps} />
        </MainLayout>
      </AuthProvider>
    </ConfigProvider>
  );
}

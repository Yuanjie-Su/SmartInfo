// @frontend/src/pages/_app.tsx
import React, { useEffect } from 'react';
import type { AppProps } from 'next/app';
import { ConfigProvider, Spin } from 'antd'; // Import Spin
import MainLayout from '@/components/layout/MainLayout';
import { AuthProvider, useAuth } from '@/context/AuthContext';
import { useRouter } from 'next/router';
import '@/styles/globals.css';

const publicPaths = ['/login', '/register'];

// Define a component that consumes the auth context
function AppContent({ Component, pageProps, router }: AppProps) { // Added router prop here
    const { isAuthenticated, loading } = useAuth();

    useEffect(() => {
        // Redirect authenticated users trying to access public paths
        if (!loading && isAuthenticated && publicPaths.includes(router.pathname)) {
            router.replace('/');
        }
    }, [isAuthenticated, loading, router]);

    // --- Loading Gate ---
    // While the AuthProvider is checking the initial auth state, show a global loader
    if (loading) {
        return (
            <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh' }}>
                <Spin size="large" tip="Initializing..." />
            </div>
        );
    }

    // --- Conditional Layout Rendering (Runs only after loading is false) ---
    const isPublicPath = publicPaths.includes(router.pathname);

    if (isPublicPath) {
        // Render public pages directly (login/register)
        // The useEffect above handles redirecting away if already logged in
        return <Component {...pageProps} />;
    } else {
        // Render private pages within MainLayout
        // The actual page component should be wrapped with withAuth HOC
        // to handle its specific loading/redirect logic AFTER this initial check
        return (
            <MainLayout>
                <Component {...pageProps} />
            </MainLayout>
        );
    }
}

// Main App component remains mostly the same, wrapping everything in AuthProvider
export default function App({ Component, pageProps, router }: AppProps) { // Added router prop here
    return (
        <ConfigProvider
            theme={{
                token: {
                    colorPrimary: '#1677ff',
                },
            }}
        >
            <AuthProvider>
                {/* Pass router instance to AppContent if needed, though it uses useRouter hook */}
                <AppContent Component={Component} pageProps={pageProps} router={router} /> {/* Passed router here */}
            </AuthProvider>
        </ConfigProvider>
    );
}

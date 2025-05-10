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
export default function App({ Component, pageProps, router }: AppProps & { router: ReturnType<typeof useRouter> }) {
    return (
        <ConfigProvider
            theme={{
                token: {
                    colorPrimary: 'var(--accent-color)', // #007BFF
                    colorInfo: 'var(--accent-color)',
                    colorSuccess: '#10B981',
                    colorWarning: '#F59E0B',
                    colorError: '#EF4444',

                    colorText: 'var(--text-primary)',
                    colorTextSecondary: 'var(--text-secondary)',
                    colorTextTertiary: 'var(--text-tertiary)', // For placeholders, disabled text
                    colorTextQuaternary: '#CED4DA', // Even lighter disabled text

                    colorBgContainer: 'var(--primary-bg)',    // Cards, Modals, Input backgrounds
                    colorBgLayout: 'var(--secondary-bg)',      // Overall Layout background (Sider, Header)
                    colorBgElevated: 'var(--primary-bg)',    // Popovers, Dropdowns (usually white)
                    colorBgSpotlight: '#4A5568',  // Tooltip background (darker for contrast)

                    colorBorder: 'var(--border-color)',        // Default borders
                    colorBorderSecondary: 'var(--border-color-secondary)',// Lighter borders (dividers)

                    borderRadius: 6,
                    borderRadiusLG: 8, // Cards, Modals
                    borderRadiusSM: 4, // Tags, smaller elements

                    fontFamily: "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, 'Noto Sans', sans-serif, 'Apple Color Emoji', 'Segoe UI Emoji', 'Segoe UI Symbol', 'Noto Color Emoji'",
                    fontSize: 14,

                    // Control heights for inputs, buttons for consistent sizing
                    controlHeight: 36, // Slightly larger for a more modern feel (AntD default is 32)
                    controlHeightLG: 40,
                    controlHeightSM: 30,

                    // Shadows
                    boxShadow: '0 1px 2px 0 rgba(0, 0, 0, 0.03), 0 1px 6px -1px rgba(0, 0, 0, 0.02), 0 2px 4px 0 rgba(0, 0, 0, 0.02)', // Subtle base shadow
                },
                components: {
                    Layout: {
                        siderBg: 'var(--secondary-bg)', // Sider background
                        bodyBg: 'var(--primary-bg)',   // Main content area background (Layout > Content)
                        headerBg: 'var(--primary-bg)', // If a header is used
                    },
                    Menu: {
                        itemBg: 'transparent', // Sider menu item background
                        itemHoverBg: 'var(--tertiary-bg)', // var(--tertiary-bg)
                        itemSelectedBg: 'var(--accent-color-light)', // var(--accent-color-light)
                        itemSelectedColor: 'var(--accent-color)', // var(--accent-color)
                        itemColor: 'var(--text-secondary)', // Slightly darker than colorTextSecondary for better readability in Sider
                        itemHoverColor: 'var(--text-primary)', // var(--text-primary)
                        activeBarBorderWidth: 0, // Remove if not using horizontal menu
                        // Add a way to style the left border for selected items if possible via tokens
                        // Otherwise, CSS override is needed.
                    },
                    Card: {
                        actionsBg: '#FDFDFD',
                        paddingLG: 20, // Content padding inside card
                        extraColor: 'var(--text-secondary)', // Color for "extra" content in card header
                    },
                    Button: {
                        // Primary button text color is usually white, handled by AntD
                        defaultBg: 'var(--primary-bg)',
                        defaultColor: 'var(--text-primary)',
                        defaultBorderColor: 'var(--border-color)',
                        defaultGhostColor: 'var(--text-primary)', // Text color for ghost buttons
                        defaultGhostBorderColor: 'var(--border-color)',
                    },
                    Input: {
                        colorBgContainer: 'var(--input-bg)',
                        colorBorder: 'var(--input-border-color)',
                        colorTextPlaceholder: 'var(--input-placeholder-color)',
                        // controlHeight: 36, // Set globally
                    },
                    Select: {
                        // controlHeight: 36, // Set globally
                    },
                    Tooltip: {
                        colorBgSpotlight: '#2D3748', // Darker tooltip background
                        colorTextLightSolid: '#FFFFFF', // Text color for dark tooltips
                    }
                }
            }}
        >
            <AuthProvider>
                <AppContent Component={Component} pageProps={pageProps} router={router} />
            </AuthProvider>
        </ConfigProvider>
    );
}

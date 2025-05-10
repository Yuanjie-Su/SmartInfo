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
                    colorPrimary: '#3B82F6', // Accent Color
                    colorInfo: '#3B82F6',
                    colorSuccess: '#10B981',
                    colorWarning: '#F59E0B',
                    colorError: '#EF4444',

                    colorText: '#212529',
                    colorTextSecondary: '#6C757D',
                    colorTextTertiary: '#ADB5BD', // For placeholders, disabled text
                    colorTextQuaternary: '#CED4DA', // Even lighter disabled text

                    colorBgContainer: '#FFFFFF',    // Cards, Modals, Input backgrounds
                    colorBgLayout: '#F8F9FA',      // Overall Layout background (Sider, Header)
                    colorBgElevated: '#FFFFFF',    // Popovers, Dropdowns (usually white)
                    colorBgSpotlight: '#4A5568',  // Tooltip background (darker for contrast)

                    colorBorder: '#DEE2E6',        // Default borders
                    colorBorderSecondary: '#E9ECEF',// Lighter borders (dividers)

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
                    boxShadowCard: '0 2px 8px rgba(0, 0, 0, 0.06)', // For cards
                    boxShadowSecondary: '0 6px 16px 0 rgba(0, 0, 0, 0.08), 0 3px 6px -4px rgba(0, 0, 0, 0.12), 0 9px 28px 8px rgba(0, 0, 0, 0.05)', // Popups
                },
                components: {
                    Layout: {
                        siderBg: '#F8F9FA', // Sider background
                        bodyBg: '#F8F9FA',   // Main content area background (Layout > Content)
                        headerBg: '#FFFFFF', // If a header is used
                    },
                    Menu: {
                        itemBg: 'transparent', // Sider menu item background
                        itemHoverBg: '#F1F3F5', // var(--tertiary-bg)
                        itemSelectedBg: '#EFF6FF', // var(--accent-color-light)
                        itemSelectedColor: '#3B82F6', // var(--accent-color)
                        itemColor: '#4A5568', // Slightly darker than colorTextSecondary for better readability in Sider
                        itemHoverColor: '#212529', // var(--text-primary)
                        activeBarBorderWidth: 0, // Remove if not using horizontal menu
                        // Add a way to style the left border for selected items if possible via tokens
                        // Otherwise, CSS override is needed.
                    },
                    Card: {
                        actionsBg: '#FDFDFD',
                        paddingLG: 20, // Content padding inside card
                        extraColor: '#6C757D', // Color for "extra" content in card header
                    },
                    Button: {
                        // Primary button text color is usually white, handled by AntD
                        defaultGhostColor: '#212529', // Text color for ghost buttons
                        defaultGhostBorderColor: '#DEE2E6',
                    },
                    Input: {
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

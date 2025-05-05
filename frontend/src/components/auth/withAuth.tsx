import React, { useEffect } from 'react';
import { useRouter } from 'next/router';
import { useAuth } from '@/context/AuthContext';
import { Spin } from 'antd'; // For loading indicator

// Define the props for the HOC
interface WithAuthProps {
    // You can add any additional props needed by the HOC itself
}

// The HOC function
const withAuth = <P extends object>(WrappedComponent: React.ComponentType<P>) => {
    const ComponentWithAuth: React.FC<P & WithAuthProps> = (props) => {
        const { isAuthenticated, loading } = useAuth();
        const router = useRouter();

        useEffect(() => {
            // Redirect to login if not authenticated and not loading
            if (!loading && !isAuthenticated) {
                console.log('withAuth: Not authenticated, redirecting to /login');
                router.replace('/login'); // Use replace to avoid adding login page to history stack
            } else if (!loading && isAuthenticated) {
                console.log('withAuth: Authenticated, rendering component.');
            }
        }, [isAuthenticated, loading, router]);

        // Show loading indicator while checking auth status
        if (loading) {
            return (
                <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh' }}>
                    <Spin size="large" tip="Loading..." />
                </div>
            );
        }

        // If authenticated, render the wrapped component
        // Otherwise, render null (or the loading spinner) while redirecting
        return isAuthenticated ? <WrappedComponent {...props} /> : null;
    };

    // Set display name for better debugging
    ComponentWithAuth.displayName = `WithAuth(${WrappedComponent.displayName || WrappedComponent.name || 'Component'})`;

    return ComponentWithAuth;
};

export default withAuth;

import React, { createContext, useState, useContext, useEffect, ReactNode } from 'react';
import { useRouter } from 'next/router';
// Import actual service functions
import { loginUser, logoutUser /*, fetchUserProfile */ } from '../services/authService';
import api from '../services/api'; // Import api to potentially clear auth header on logout error

// Define the shape of the user object (adjust as needed based on backend response)
interface User {
  id: string;
  username: string;
  // Add other relevant user fields if returned by backend (e.g., email, roles)
}

// Define the shape of the context value
interface AuthContextType {
  isAuthenticated: boolean;
  user: User | null;
  token: string | null;
  loading: boolean; // Indicates initial auth check or ongoing login/logout
  login: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>; // Make logout async
  // signup?: (userData: any) => Promise<void>; // Optional signup function
}

// Create the context with a default value
const AuthContext = createContext<AuthContextType | undefined>(undefined);

// Define the props for the AuthProvider component
interface AuthProviderProps {
  children: ReactNode;
}

// Create the AuthProvider component
export const AuthProvider: React.FC<AuthProviderProps> = ({ children }) => {
  const [isAuthenticated, setIsAuthenticated] = useState<boolean>(false);
  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [loading, setLoading] = useState<boolean>(true); // Start loading until initial check is done
  const router = useRouter();

  // Effect to check for existing token on mount and validate it
  useEffect(() => {
    const validateToken = async () => {
      const storedToken = localStorage.getItem('authToken');
      if (storedToken) {
        console.log("Found token in localStorage. Validating...");
        setToken(storedToken); // Temporarily set token for API calls
        try {
          // TODO: Uncomment and use actual profile fetching function if available
          // const fetchedUser = await fetchUserProfile();
          // --- Placeholder for user fetch ---
          // Simulate fetching user based on token - replace with actual call
          const fetchedUser: User = { id: 'temp-id-from-token', username: 'user-from-token' };
          console.log("Token validation successful (simulated). User:", fetchedUser);
          // --- End Placeholder ---

          setUser(fetchedUser);
          setIsAuthenticated(true);
          console.log("Auth state initialized from validated token.");
        } catch (error: any) {
          console.error("Token validation failed:", error.message);
          localStorage.removeItem('authToken');
          setToken(null);
          setUser(null);
          setIsAuthenticated(false);
          // Optionally clear Authorization header from default Axios instance if validation fails
          if (api.defaults.headers.common['Authorization']) {
            delete api.defaults.headers.common['Authorization'];
          }
        }
      } else {
        console.log("No token found in localStorage.");
        setIsAuthenticated(false);
        setUser(null);
        setToken(null);
      }
      setLoading(false); // Finished initial check/validation
    };

    validateToken();
  }, []); // Run only once on mount

  const login = async (username: string, password: string) => {
    setLoading(true);
    try {
      console.log(`Attempting login for user: ${username}`);
      // Call the actual API service
      const { token: receivedToken, user: loggedInUser } = await loginUser({ username, password });

      localStorage.setItem('authToken', receivedToken);
      setToken(receivedToken);
      setUser(loggedInUser); // Assuming backend returns user object on login
      setIsAuthenticated(true);
      console.log("Login successful, token stored.");

      // Redirect to the page the user was trying to access, or home
      const returnUrl = (router.query.returnUrl as string) || '/';
      router.push(returnUrl);

    } catch (error) {
      console.error('Login failed:', error);
      // Clear any potentially partially set state
      localStorage.removeItem('authToken');
      setToken(null);
      setUser(null);
      setIsAuthenticated(false);
      // Rethrow the error so the login page can display it
      throw error;
    } finally {
      setLoading(false);
    }
  };

  const logout = async () => {
    setLoading(true);
    console.log("Logging out user.");
    try {
      // Optional: Call backend logout endpoint if it exists/is needed
      // await logoutUser();
      console.log("Backend logout call skipped/successful (if implemented).");
    } catch (error) {
        console.error('Backend logout failed:', error);
        // Decide if logout should proceed even if backend call fails
        // message.error("Logout failed on server, but logging out locally.");
    } finally {
        // Always clear local state and storage regardless of backend call success
        localStorage.removeItem('authToken');
        setToken(null);
        setUser(null);
        setIsAuthenticated(false);
        // Optionally clear Authorization header from default Axios instance
        if (api.defaults.headers.common['Authorization']) {
            delete api.defaults.headers.common['Authorization'];
        }
        console.log("Token removed, state reset.");
        setLoading(false);
        // Redirect to login page after logout
        router.push('/login');
    }
  };

  // Optional signup function
  // const signup = async (userData: any) => { ... };

  const contextValue: AuthContextType = {
    isAuthenticated,
    user,
    token,
    loading,
    login,
    logout,
    // signup,
  };

  // Render children only after initial loading is complete
  // or wrap children in a loading check if preferred
  return (
    <AuthContext.Provider value={contextValue}>
      {/* {!loading ? children : <Spin tip="Initializing..." />} */}
      {children}
    </AuthContext.Provider>
  );
};

// Custom hook to use the AuthContext
export const useAuth = (): AuthContextType => {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};

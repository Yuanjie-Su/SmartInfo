import React, { createContext, useState, useContext, useEffect, ReactNode } from 'react';
import { useRouter } from 'next/router';
// Import actual service functions
import { loginUser, logoutUser, registerUser, fetchUserProfile, User as UserType } from '../services/authService';
import api from '../services/api'; // Import api to potentially clear auth header on logout error

// Define the shape of the user object based on service type
type User = UserType;

// Define the shape of the context value
interface AuthContextType {
  isAuthenticated: boolean;
  user: User | null;
  token: string | null;
  loading: boolean; // Indicates initial auth check or ongoing login/logout
  login: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>; // Make logout async
  signup: (username: string, password: string) => Promise<void>; // Implementation of signup function
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
        // 设置令牌用于API调用
        setToken(storedToken);
        api.defaults.headers.common['Authorization'] = `Bearer ${storedToken}`;
        
        try {
          // 使用真实API调用检查令牌是否有效
          const fetchedUser = await fetchUserProfile();
          console.log("Token validation successful. User:", fetchedUser);
          
          // 设置验证后的用户状态
          setUser(fetchedUser);
          setIsAuthenticated(true);
          console.log("Auth state initialized from validated token.");
        } catch (error: any) {
          console.error("Token validation failed:", error.message);
          // 清除无效的令牌和用户信息
          localStorage.removeItem('authToken');
          setToken(null);
          setUser(null);
          setIsAuthenticated(false);
          // 清除 Axios 默认认证头
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

  // 更新API认证头的额外效果
  useEffect(() => {
    if (token) {
      api.defaults.headers.common['Authorization'] = `Bearer ${token}`;
    } else if (api.defaults.headers.common['Authorization']) {
      delete api.defaults.headers.common['Authorization'];
    }
  }, [token]);

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

  const signup = async (username: string, password: string) => {
    setLoading(true);
    try {
      console.log(`Attempting to register user: ${username}`);
      
      // Call the registration service function
      await registerUser({ username, password });
      
      console.log("Registration successful");
      
      // Registration successful, automatically login the user
      // Or simply return and let the signup page redirect to login
      return;
      
    } catch (error) {
      console.error('Registration failed:', error);
      // Rethrow the error so the registration page can display it
      throw error;
    } finally {
      setLoading(false);
    }
  };

  const contextValue: AuthContextType = {
    isAuthenticated,
    user,
    token,
    loading,
    login,
    logout,
    signup,
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

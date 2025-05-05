import api from './api'; // Import the configured Axios instance
import { handleApiError } from '../utils/apiErrorHandler'; // Import error handler

// Define the expected shape of login credentials
interface LoginCredentials {
    username: string;
    password: string;
}

// Define the expected shape of the login response (adjust based on backend)
interface LoginResponse {
    token: string;
    user: {
        id: string;
        username: string;
        // other user fields
    };
}

// Define the expected shape of signup data (adjust based on backend)
interface SignupData {
    username: string;
    password: string;
    // other required fields
}

// Define the expected shape of the signup response (adjust based on backend)
interface SignupResponse {
    message: string; // e.g., "User created successfully"
    user?: { // Optional: backend might return the created user
        id: string;
        username: string;
    };
}


/**
 * Calls the backend API to log in a user.
 * @param credentials - The user's login credentials (username, password).
 * @returns A promise that resolves with the login response (token, user data).
 */
export const loginUser = async (credentials: LoginCredentials): Promise<LoginResponse> => {
    try {
        // TODO: Replace '/api/auth/login' with the actual backend endpoint
        // Using a placeholder URL for now as the backend isn't specified
        console.warn("Using placeholder API endpoint for login: /api/auth/login");
        const response = await api.post<LoginResponse>('/api/auth/login', credentials);
        return response.data;
    } catch (error) {
        // Use the centralized error handler
        throw handleApiError(error, 'Login failed');
    }
};

/**
 * Calls the backend API to log out a user.
 * (This might not be strictly necessary if logout is purely client-side token removal,
 * but often includes invalidating the token on the backend).
 * @returns A promise that resolves when the logout is complete.
 */
export const logoutUser = async (): Promise<void> => {
    try {
        // TODO: Replace '/api/auth/logout' with the actual backend endpoint if needed
        // This endpoint might not exist or might not be required depending on backend implementation
        // await api.post('/api/auth/logout');
        console.log("Logout request potentially sent to /api/auth/logout (if implemented).");
    } catch (error) {
        // Use the centralized error handler
        throw handleApiError(error, 'Logout failed');
    }
};

/**
 * Calls the backend API to register a new user.
 * @param userData - The data for the new user.
 * @returns A promise that resolves with the signup response.
 */
export const registerUser = async (userData: SignupData): Promise<SignupResponse> => {
    try {
        // TODO: Replace '/api/auth/register' or '/api/auth/signup' with the actual backend endpoint
        console.warn("Using placeholder API endpoint for registration: /api/auth/register");
        const response = await api.post<SignupResponse>('/api/auth/register', userData);
        return response.data;
    } catch (error) {
        // Use the centralized error handler
        throw handleApiError(error, 'Registration failed');
    }
};

// Optional: Function to validate token / fetch user profile
// interface User { id: string; username: string; /* ... */ }
// export const fetchUserProfile = async (): Promise<User> => {
//   try {
//     console.warn("Using placeholder API endpoint for profile fetch: /api/auth/profile");
//     const response = await api.get<User>('/api/auth/profile');
//     return response.data;
//   } catch (error) {
//     throw handleApiError(error, 'Failed to fetch user profile');
//   }
// }

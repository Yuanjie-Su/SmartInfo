import api from './api'; // Import the configured Axios instance
import { handleApiError } from '../utils/apiErrorHandler'; // Import error handler

// Define the expected shape of login credentials
interface LoginCredentials {
    username: string;
    password: string;
}

// Define the expected shape of the login response (adjust based on backend)
interface LoginResponse {
    access_token: string; // Changed from 'token' to 'access_token'
    token_type: string; // Added token_type as per backend response
    user: User; // Use the imported User type
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

// Define the User interface for profile data
export interface User {
    id: string;
    username: string;
    // other user fields that the backend might return
}

/**
 * Calls the backend API to log in a user.
 * @param credentials - The user's login credentials (username, password).
 * @returns A promise that resolves with the login response (token, user data).
 */
export const loginUser = async (credentials: LoginCredentials): Promise<LoginResponse> => {
    try {
        // Send credentials as form data, as required by the backend's OAuth2PasswordRequestForm
        const formData = new URLSearchParams();
        formData.append('username', credentials.username);
        formData.append('password', credentials.password);

        const response = await api.post<LoginResponse>('/api/auth/token', formData, {
            headers: {
                'Content-Type': 'application/x-www-form-urlencoded'
            }
        });
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
        const response = await api.post<SignupResponse>('/api/auth/register', userData);
        return response.data;
    } catch (error) {
        // Use the centralized error handler
        throw handleApiError(error, 'Registration failed');
    }
};

/**
 * Fetches current user profile using the stored authentication token.
 * This is used to validate if the token is still valid and get current user data.
 * @returns A promise that resolves with the user profile data.
 */
export const fetchUserProfile = async (): Promise<User> => {
    try {
        // Call the /users/me endpoint which is standard in FastAPI applications
        const response = await api.get<User>('/api/auth/users/me');
        return response.data;
    } catch (error) {
        throw handleApiError(error, 'Failed to fetch user profile');
    }
}

import axios, { AxiosHeaders } from 'axios'; // Import AxiosHeaders

// Base API configuration
const api = axios.create({
  baseURL: process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000',
  headers: {
    'Content-Type': 'application/json',
  },
  timeout: 10000, // Add timeout to prevent hanging requests
});

// Request interceptor for adding auth token or other headers if needed
api.interceptors.request.use(
  (config) => {
    // Retrieve the token from localStorage
    const token = localStorage.getItem('authToken');

    // If the token exists, add it to the Authorization header
    if (token) {
      // Ensure headers object exists (Axios should initialize it, but let's be safe)
      if (!config.headers) {
        config.headers = new AxiosHeaders(); // Initialize with the correct class
      }
      // Use the 'set' method for type safety
      config.headers.set('Authorization', `Bearer ${token}`);
      // console.log('Token added to request headers:', config.headers.get('Authorization')); // Optional: for debugging
    } else {
      // console.log('No token found, request sent without Authorization header.'); // Optional: for debugging
    }

    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

// Response interceptor for global error handling
api.interceptors.response.use(
  (response) => {
    return response;
  },
  (error) => {
    // Check if the error is a network error
    if (error.message === 'Network Error') {
      console.error('Network error detected - server might be down or unreachable');
    } else {
      console.error('API Error:', error.response?.data || error.message);
    }

    // Check for 401 Unauthorized errors
    if (error.response?.status === 401) {
      console.warn('401 Unauthorized error detected.');
      // Check if the request was NOT to the login endpoint
      if (error.config && error.config.url !== '/api/auth/token') {
        console.log('401 on a non-login endpoint, dispatching auth-error event.');
        // Dispatch a custom event to trigger logout in AuthContext
        window.dispatchEvent(new CustomEvent('auth-error', { detail: { type: 'token-expired' } }));
      } else {
        console.log('401 on login endpoint, not dispatching auth-error.');
      }
    }

    return Promise.reject(error);
  }
);

export default api;

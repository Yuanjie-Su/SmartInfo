import { message } from 'antd';
import axios, { AxiosError } from 'axios';

/**
 * Utility function to extract and format error messages from API errors
 */
export const extractErrorMessage = (error: unknown): string => {
  if (axios.isAxiosError(error)) {
    const axiosError = error as AxiosError;
    
    // Error from the server with a response
    if (axiosError.response?.data) {
      const data = axiosError.response.data as any;
      if (data.detail) {
        return data.detail;
      }
      if (typeof data === 'string') {
        return data;
      }
    }
    
    // Network error or no response
    if (axiosError.message) {
      return axiosError.message;
    }
  }
  
  // Default fallback for non-Axios errors
  if (error instanceof Error) {
    return error.message;
  }
  
  return 'An unknown error occurred';
};

/**
 * Utility function to handle API errors with Ant Design message notification
 */
export const handleApiError = (error: unknown, customMessage?: string): void => {
  const errorMessage = extractErrorMessage(error);
  message.error(customMessage ? `${customMessage}: ${errorMessage}` : errorMessage);
};

/**
 * Higher-order function to wrap an async API call with error handling
 */
export const withErrorHandling = async <T>(
  apiCall: () => Promise<T>,
  errorHandler?: (error: unknown) => void,
  customErrorMessage?: string
): Promise<T | null> => {
  try {
    return await apiCall();
  } catch (error) {
    if (errorHandler) {
      errorHandler(error);
    } else {
      handleApiError(error, customErrorMessage);
    }
    return null;
  }
}; 
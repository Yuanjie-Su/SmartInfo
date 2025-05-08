import { message } from 'antd';
import axios, { AxiosError } from 'axios';

/**
 * Utility function to extract and format error messages from API errors
 * Returns a structured object for specific error types (404, 403) or a generic one.
 */
export const extractErrorMessage = (error: unknown): { type: string, message: string, status?: number } => {
  if (axios.isAxiosError(error)) {
    const axiosError = error as AxiosError<any>; // Allow any type for data
    const status = axiosError.response?.status;
    const data = axiosError.response?.data;
    let messageText = axiosError.message; // Default to Axios message

    if (status === 404) {
      return { type: 'notFound', message: data?.detail || 'Resource not found', status };
    }
    if (status === 403) {
      return { type: 'forbidden', message: data?.detail || 'Access forbidden', status };
    }
    if (data?.detail) {
      messageText = data.detail; // Use detail from backend if available
    } else if (typeof data === 'string') {
      messageText = data; // Use raw string data if available
    }

    // For other Axios errors (400, 500, network, etc.)
    return { type: 'apiError', message: messageText, status };
  }

  // Default fallback for non-Axios errors
  if (error instanceof Error) {
    return { type: 'unknown', message: error.message };
  }

  return { type: 'unknown', message: 'An unknown error occurred' };
};

/**
 * Utility function to handle API errors with Ant Design message notification
 * Avoids showing global messages for 404/403 errors.
 */
export const handleApiError = (error: unknown, customMessage?: string): void => {
  const errorDetails = extractErrorMessage(error);

  // Log 404/403 errors to console instead of showing a global message
  if (errorDetails.type === 'notFound' || errorDetails.type === 'forbidden') {
    console.error(`API Error (${errorDetails.status}):`, errorDetails.message, error);
  } else {
    // Show global message for other errors (network, 5xx, 400, etc.)
    message.error(customMessage ? `${customMessage}: ${errorDetails.message}` : errorDetails.message);
  }
};

/**
 * Higher-order function to wrap an async API call with error handling
 * Returns null for 404/403 errors, re-throws others after handling.
 */
export const withErrorHandling = async <T>(
  apiCall: () => Promise<T>,
  errorHandler?: (error: { type: string, message: string, status?: number }) => void, // Custom handler for specific component needs
  customErrorMessage?: string
): Promise<T | null> => {
  try {
    return await apiCall();
  } catch (error) {
    const errorDetails = extractErrorMessage(error);

    if (errorHandler) {
      // If a custom handler is provided, let it handle the error
      errorHandler(errorDetails); // Pass the structured error details
    } else {
      // Otherwise, use the default global handler
      handleApiError(error, customErrorMessage);
    }

    // Return null for notFound and forbidden errors as per the plan
    if (errorDetails.type === 'notFound' || errorDetails.type === 'forbidden') {
      return null;
    }

    // For other errors, re-throw after handling (if not handled by custom handler)
    // This allows components to catch specific errors if needed, or lets the default handler take over.
    // If a custom handler was used, it's up to the handler to decide whether to re-throw.
    // For simplicity here, let's assume if a custom handler is provided, it fully handles the error and we don't re-throw here.
    // If no custom handler, handleApiError shows the message, and we re-throw for component catch blocks.
    if (!errorHandler) {
      throw error; // Re-throw the original error object
    }

    return null; // If custom handler was used, assume it handled it and return null
  }
};

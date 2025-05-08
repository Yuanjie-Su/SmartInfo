import api from './api';
import axios from 'axios'; // Import axios for error checking
import { ApiKey, ApiKeyCreate, UserPreferenceUpdate } from '../utils/types';

const BASE_PATH = '/api/settings';

// System Settings API
export const getSettings = async (): Promise<Record<string, any>> => {
  const response = await api.get(`${BASE_PATH}/settings`);
  return response.data;
};

export const updateSettings = async (settings: Record<string, any>): Promise<Record<string, any>> => {
  const settingsUpdate: UserPreferenceUpdate = { settings };
  const response = await api.put(`${BASE_PATH}/settings`, settingsUpdate);
  return response.data;
};

export const resetSettings = async (): Promise<Record<string, any>> => {
  const response = await api.post(`${BASE_PATH}/settings/reset`);
  return response.data;
};

// API Keys API
export const getApiKeys = async (): Promise<ApiKey[]> => {
  const response = await api.get(`${BASE_PATH}/api_keys`);
  return response.data;
};

export const createApiKey = async (apiKey: ApiKeyCreate): Promise<ApiKey> => {
  const response = await api.post(`${BASE_PATH}/api_keys`, apiKey);
  return response.data;
};

export const getApiKey = async (apiKeyId: number): Promise<ApiKey | null> => {
  try {
    const response = await api.get<ApiKey>(`${BASE_PATH}/api_keys/${apiKeyId}`);
    return response.data;
  } catch (error) {
    if (axios.isAxiosError(error) && error.response?.status === 404) {
      console.warn(`SettingsService: API Key with ID ${apiKeyId} not found (404).`);
      return null; // Return null for not found
    }
    // Re-throw other errors (network, 5xx, etc.)
    console.error(`SettingsService: Error fetching API Key ${apiKeyId}:`, error);
    throw error;
  }
};

export const updateApiKey = async (apiKeyId: number, apiKey: ApiKeyCreate): Promise<ApiKey> => {
  const response = await api.put(`${BASE_PATH}/api_keys/${apiKeyId}`, apiKey);
  return response.data;
};

export const deleteApiKey = async (apiKeyId: number): Promise<void> => {
  await api.delete(`${BASE_PATH}/api_keys/${apiKeyId}`);
};

// API Key Test Functionality
export const testApiKey = async (apiKeyId: number): Promise<Record<string, any>> => {
  const response = await api.post(`${BASE_PATH}/api_keys/${apiKeyId}/test`);
  return response.data;
};

// LLM Service Test
export const testLlmService = async (): Promise<Record<string, any>> => {
  const response = await api.get(`${BASE_PATH}/llm/test`);
  return response.data;
};

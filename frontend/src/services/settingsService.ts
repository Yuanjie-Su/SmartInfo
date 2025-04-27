import api from './api';
import { ApiKey, ApiKeyCreate, SystemConfigUpdate } from '../utils/types';

const BASE_PATH = '/api/settings';

// System Settings API
export const getSettings = async (): Promise<Record<string, any>> => {
  const response = await api.get(`${BASE_PATH}/settings`);
  return response.data;
};

export const updateSettings = async (settings: Record<string, any>): Promise<Record<string, any>> => {
  const settingsUpdate: SystemConfigUpdate = { settings };
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

export const getApiKey = async (apiName: string): Promise<ApiKey> => {
  const response = await api.get(`${BASE_PATH}/api_keys/${apiName}`);
  return response.data;
};

export const updateApiKey = async (apiName: string, apiKey: ApiKeyCreate): Promise<ApiKey> => {
  const response = await api.put(`${BASE_PATH}/api_keys/${apiName}`, apiKey);
  return response.data;
};

export const deleteApiKey = async (apiName: string): Promise<void> => {
  await api.delete(`${BASE_PATH}/api_keys/${apiName}`);
};

// LLM Service Test
export const testLlmService = async (): Promise<Record<string, any>> => {
  const response = await api.get(`${BASE_PATH}/llm/test`);
  return response.data;
}; 
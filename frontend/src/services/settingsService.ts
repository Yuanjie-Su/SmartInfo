import api from './api';
import { ApiKey, ApiKeyCreate, SettingsUpdate } from '../utils/types';

const BASE_PATH = '/settings';

// Settings API
export const getSettings = async (): Promise<Record<string, any>> => {
  const response = await api.get(`${BASE_PATH}/`);
  return response.data.settings;
};

export const updateSettings = async (settings: Record<string, any>): Promise<{ message: string; settings: Record<string, any> }> => {
  const settingsUpdate: SettingsUpdate = { settings };
  const response = await api.put(`${BASE_PATH}/`, settingsUpdate);
  return response.data;
};

export const resetSettings = async (): Promise<{ message: string; settings: Record<string, any> }> => {
  const response = await api.post(`${BASE_PATH}/reset`);
  return response.data;
};

// API Keys API
export const getApiKeys = async (): Promise<ApiKey[]> => {
  const response = await api.get(`${BASE_PATH}/api-keys`);
  return response.data;
};

export const createApiKey = async (apiKey: ApiKeyCreate): Promise<ApiKey> => {
  const response = await api.post(`${BASE_PATH}/api-keys`, apiKey);
  return response.data;
};

export const getApiKey = async (apiName: string): Promise<ApiKey> => {
  const response = await api.get(`${BASE_PATH}/api-keys/${apiName}`);
  return response.data;
};

export const updateApiKey = async (apiName: string, apiKey: ApiKeyCreate): Promise<ApiKey> => {
  const response = await api.put(`${BASE_PATH}/api-keys/${apiName}`, apiKey);
  return response.data;
};

export const deleteApiKey = async (apiName: string): Promise<void> => {
  await api.delete(`${BASE_PATH}/api-keys/${apiName}`);
}; 
import { create } from 'zustand';
import { ApiKey, SystemConfig, ApiKeyCreate, SystemConfigCreate } from '../types/settings';
import { settingsApi } from '../services/api';

interface SettingsState {
    apiKeys: ApiKey[];
    systemConfigs: SystemConfig[];
    isLoading: boolean;
    error: string | null;

    // API Keys actions
    fetchApiKeys: () => Promise<void>;
    createApiKey: (apiKey: ApiKeyCreate) => Promise<void>;
    updateApiKey: (service: string, key: string) => Promise<void>;
    deleteApiKey: (service: string) => Promise<void>;

    // System Config actions
    fetchSystemConfigs: () => Promise<void>;
    createSystemConfig: (config: SystemConfigCreate) => Promise<void>;
    updateSystemConfig: (key: string, value: any) => Promise<void>;
    deleteSystemConfig: (key: string) => Promise<void>;
}

export const useSettingsStore = create<SettingsState>((set) => ({
    apiKeys: [],
    systemConfigs: [],
    isLoading: false,
    error: null,

    // API Keys actions
    fetchApiKeys: async () => {
        try {
            set({ isLoading: true, error: null });
            const apiKeys = await settingsApi.getApiKeys();
            set({ apiKeys, isLoading: false });
        } catch (error) {
            set({
                error: error instanceof Error ? error.message : '获取API密钥失败',
                isLoading: false
            });
        }
    },

    createApiKey: async (apiKey) => {
        try {
            set({ isLoading: true, error: null });
            await settingsApi.createApiKey(apiKey);
            const apiKeys = await settingsApi.getApiKeys();
            set({ apiKeys, isLoading: false });
        } catch (error) {
            set({
                error: error instanceof Error ? error.message : '创建API密钥失败',
                isLoading: false
            });
        }
    },

    updateApiKey: async (service, key) => {
        try {
            set({ isLoading: true, error: null });
            await settingsApi.updateApiKey(service, key);
            const apiKeys = await settingsApi.getApiKeys();
            set({ apiKeys, isLoading: false });
        } catch (error) {
            set({
                error: error instanceof Error ? error.message : '更新API密钥失败',
                isLoading: false
            });
        }
    },

    deleteApiKey: async (service) => {
        try {
            set({ isLoading: true, error: null });
            await settingsApi.deleteApiKey(service);
            const apiKeys = await settingsApi.getApiKeys();
            set({ apiKeys, isLoading: false });
        } catch (error) {
            set({
                error: error instanceof Error ? error.message : '删除API密钥失败',
                isLoading: false
            });
        }
    },

    // System Config actions
    fetchSystemConfigs: async () => {
        try {
            set({ isLoading: true, error: null });
            const systemConfigs = await settingsApi.getSystemConfigs();
            set({ systemConfigs, isLoading: false });
        } catch (error) {
            set({
                error: error instanceof Error ? error.message : '获取系统配置失败',
                isLoading: false
            });
        }
    },

    createSystemConfig: async (config) => {
        try {
            set({ isLoading: true, error: null });
            await settingsApi.createSystemConfig(config);
            const systemConfigs = await settingsApi.getSystemConfigs();
            set({ systemConfigs, isLoading: false });
        } catch (error) {
            set({
                error: error instanceof Error ? error.message : '创建系统配置失败',
                isLoading: false
            });
        }
    },

    updateSystemConfig: async (key, value) => {
        try {
            set({ isLoading: true, error: null });
            await settingsApi.updateSystemConfig(key, value);
            const systemConfigs = await settingsApi.getSystemConfigs();
            set({ systemConfigs, isLoading: false });
        } catch (error) {
            set({
                error: error instanceof Error ? error.message : '更新系统配置失败',
                isLoading: false
            });
        }
    },

    deleteSystemConfig: async (key) => {
        try {
            set({ isLoading: true, error: null });
            await settingsApi.deleteSystemConfig(key);
            const systemConfigs = await settingsApi.getSystemConfigs();
            set({ systemConfigs, isLoading: false });
        } catch (error) {
            set({
                error: error instanceof Error ? error.message : '删除系统配置失败',
                isLoading: false
            });
        }
    }
})); 
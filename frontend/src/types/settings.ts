// temp/frontend/src/types/settings.ts
// Aligned with backend/api/schemas/settings.py

/**
 * Represents information about an API key (for listing).
 * Matches backend schema: ApiKeyInfo
 */
export interface ApiKeyInfo {
    api_name: string;
    created_date: string;
    modified_date: string;
}

/**
 * Represents the structure for creating/updating an API key via API.
 * Matches backend schema: ApiKeyCreate
 */
export interface ApiKeyCreate {
    api_name: string;
    api_key: string;
}

/**
 * Represents the response structure when fetching a single API key's value.
 * Matches backend GET /api/settings/api-keys/{api_name} response.
 */
export interface ApiKeyGetResponse {
    api_key: string | null;
}

/**
 * Represents a single system configuration item.
 * Matches backend schema: SystemConfig
 */
export interface SystemConfig {
    config_key: string;
    config_value: any; // Value can be diverse types (string, number, boolean, object)
    // Optional: Add description if the backend sends it and frontend needs it
    description?: string | null;
}

/**
 * Represents the structure for updating a system configuration item via API.
 * Matches backend schema: SystemConfigUpdate
 */
export interface SystemConfigUpdate {
    config_value: any;
}

/**
 * Represents the structure for creating a system configuration item (if needed).
 * Backend currently uses PUT for upsert, but this can be useful for frontend forms.
 */
export interface SystemConfigCreate {
    config_key: string;
    config_value: any;
    description?: string | null; // Optional description on creation
}

/**
 * Represents the structure for the response when getting all system configs.
 * Matches backend GET /api/settings/config response.
 */
export type AllSystemConfigs = Record<string, any>;
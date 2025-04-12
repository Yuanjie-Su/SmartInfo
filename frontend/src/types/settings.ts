export interface ApiKey {
    id: string;
    service: string;
    key: string;
    created_at: string;
    updated_at: string;
}

export interface ApiKeyCreate {
    service: string;
    key: string;
}

export interface ApiKeyUpdate {
    key: string;
}

export interface SystemConfig {
    id: string;
    key: string;
    value: any;
    created_at: string;
    updated_at: string;
}

export interface SystemConfigCreate {
    key: string;
    value: any;
}

export interface SystemConfigUpdate {
    value: any;
} 
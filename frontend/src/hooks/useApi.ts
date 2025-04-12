import { useState, useCallback, useEffect } from 'react';

interface UseApiResponse<T> {
    data: T | null;
    loading: boolean;
    error: string | null;
    execute: (...args: any[]) => Promise<T>;
}

export function useApi<T>(
    apiFunction: (...args: any[]) => Promise<T>,
    executeOnMount: boolean = false,
    initialArgs: any[] = []
): UseApiResponse<T> {
    const [data, setData] = useState<T | null>(null);
    const [loading, setLoading] = useState<boolean>(executeOnMount);
    const [error, setError] = useState<string | null>(null);

    const execute = useCallback(
        async (...args: any[]): Promise<T> => {
            setLoading(true);
            setError(null);

            try {
                const result = await apiFunction(...args);
                setData(result);
                return result;
            } catch (err) {
                const errorMessage = err instanceof Error ? err.message : '未知错误';
                setError(errorMessage);
                throw err;
            } finally {
                setLoading(false);
            }
        },
        [apiFunction]
    );

    // 如果设置了在挂载时执行
    useEffect(() => {
        if (executeOnMount) {
            execute(...initialArgs);
        }
    }, [execute, executeOnMount, initialArgs]);

    return { data, loading, error, execute };
} 
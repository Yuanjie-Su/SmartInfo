import { useState, useEffect, useCallback } from 'react';
import { WebSocketClient } from '../services/websocket';

interface UseWebSocketResponse<T> {
    connected: boolean;
    connecting: boolean;
    messages: T[];
    error: string | null;
    sendMessage: (data: any) => void;
    clearMessages: () => void;
}

export function useWebSocket<T>(
    wsClient: WebSocketClient,
    autoConnect: boolean = true
): UseWebSocketResponse<T> {
    const [connected, setConnected] = useState<boolean>(false);
    const [connecting, setConnecting] = useState<boolean>(false);
    const [messages, setMessages] = useState<T[]>([]);
    const [error, setError] = useState<string | null>(null);

    const connect = useCallback(async () => {
        if (connected || connecting) return;

        try {
            setConnecting(true);
            await wsClient.connect();
            setConnected(true);
            setError(null);
        } catch (err) {
            const errorMessage = err instanceof Error ? err.message : '连接WebSocket失败';
            setError(errorMessage);
        } finally {
            setConnecting(false);
        }
    }, [wsClient, connected, connecting]);

    const sendMessage = useCallback(
        (data: any) => {
            try {
                wsClient.send(data);
            } catch (err) {
                const errorMessage = err instanceof Error ? err.message : '发送消息失败';
                setError(errorMessage);
            }
        },
        [wsClient]
    );

    const clearMessages = useCallback(() => {
        setMessages([]);
    }, []);

    useEffect(() => {
        if (autoConnect && !connected && !connecting) {
            connect();
        }

        const removeMessageHandler = wsClient.onMessage((data: T) => {
            setMessages((prevMessages) => [...prevMessages, data]);
        });

        return () => {
            removeMessageHandler();
            wsClient.disconnect();
            setConnected(false);
        };
    }, [wsClient, autoConnect, connect, connected, connecting]);

    return {
        connected,
        connecting,
        messages,
        error,
        sendMessage,
        clearMessages
    };
} 
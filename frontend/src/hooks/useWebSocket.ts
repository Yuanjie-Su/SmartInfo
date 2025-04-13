import { useState, useEffect, useCallback, useRef } from 'react';
import { WebSocketClient } from '../services/websocket';

interface UseWebSocketResponse<T> {
    connected: boolean;
    connecting: boolean;
    messages: T[];
    error: string | null; // Store last error message
    sendMessage: (data: any) => void;
    clearMessages: () => void;
    connect: () => Promise<void>; // Expose connect/disconnect
    disconnect: () => void;
    readyState: number | null; // Expose ready state
}

export function useWebSocket<T>(
    wsClientFactory: () => WebSocketClient, // Pass a factory function
    autoConnect: boolean = true
): UseWebSocketResponse<T> {
    // Use useRef to hold the client instance to avoid re-creation on re-renders
    const wsClientRef = useRef<WebSocketClient | null>(null);
    const [connected, setConnected] = useState<boolean>(false);
    const [connecting, setConnecting] = useState<boolean>(false);
    const [messages, setMessages] = useState<T[]>([]);
    const [error, setError] = useState<string | null>(null);
    const [readyState, setReadyState] = useState<number | null>(null);

    // Function to get or create the client instance
    const getClient = useCallback(() => {
        if (!wsClientRef.current) {
            wsClientRef.current = wsClientFactory();
        }
        return wsClientRef.current;
    }, [wsClientFactory]);

    const connect = useCallback(async () => {
        const client = getClient();
        if (client.isConnected() || connecting) return;

        try {
            setConnecting(true);
            setError(null);
            setReadyState(client.getReadyState());
            await client.connect();
            setConnected(true);
        } catch (err) {
            const errorMessage = err instanceof Error ? err.message : '连接WebSocket失败';
            console.error("useWebSocket connect error:", errorMessage);
            setError(errorMessage);
            setConnected(false); // Ensure connected is false on error
        } finally {
            setConnecting(false);
            setReadyState(client.getReadyState());
        }
    }, [getClient, connecting]);

    const disconnect = useCallback(() => {
        const client = getClient();
        client.disconnect();
        setConnected(false);
        setReadyState(client.getReadyState());
    }, [getClient]);


    const sendMessage = useCallback(
        (data: any) => {
            const client = getClient();
            try {
                client.send(data);
            } catch (err) {
                const errorMessage = err instanceof Error ? err.message : '发送消息失败';
                console.error("useWebSocket sendMessage error:", errorMessage);
                setError(errorMessage); // Update error state on send failure
            }
        },
        [getClient]
    );

    const clearMessages = useCallback(() => {
        setMessages([]);
    }, []);

    // Effect for managing connection lifecycle and subscriptions
    useEffect(() => {
        const client = getClient();
        let unsubscribeMessage: (() => void) | null = null;
        let unsubscribeError: (() => void) | null = null;
        let unsubscribeClose: (() => void) | null = null;

        const setupSubscriptions = () => {
            unsubscribeMessage = client.onMessage((data: T) => {
                setMessages((prevMessages) => [...prevMessages, data]);
            });

            unsubscribeError = client.onError((errEvent: Event) => {
                console.error("WebSocket error received in hook:", errEvent);
                setError(`WebSocket error occurred. Type: ${errEvent.type}`);
                setConnected(false); // Update connected state on error
                setReadyState(client.getReadyState());
            });

            unsubscribeClose = client.onClose((closeEvent: CloseEvent) => {
                console.log(`WebSocket closed in hook. Code: ${closeEvent.code}, Reason: ${closeEvent.reason}`);
                setConnected(false);
                if (!closeEvent.wasClean) {
                    setError(`WebSocket closed unexpectedly (Code: ${closeEvent.code})`);
                }
                setReadyState(client.getReadyState());
            });
        };

        if (autoConnect) {
            connect(); // Attempt auto-connect
        }
        setupSubscriptions(); // Set up listeners regardless of autoConnect status

        // Cleanup function
        return () => {
            console.log("Cleaning up useWebSocket hook...");
            if (unsubscribeMessage) unsubscribeMessage();
            if (unsubscribeError) unsubscribeError();
            if (unsubscribeClose) unsubscribeClose();
            // Disconnect when the hook unmounts or client factory changes
            client.disconnect();
            wsClientRef.current = null; // Clear ref on unmount
        };
        // Add connect to dependency array if needed, but be careful of loops
        // If wsClientFactory changes, we want to reconnect.
    }, [getClient, autoConnect, connect]); // Removed 'connect' from deps to prevent potential loops if connect sets state causing re-render

    // Effect to update readyState when connection status changes
    useEffect(() => {
        const client = getClient();
        setReadyState(client.getReadyState());
    }, [connected, connecting, getClient]);


    return {
        connected,
        connecting,
        messages,
        error,
        sendMessage,
        clearMessages,
        connect,
        disconnect,
        readyState,
    };
}
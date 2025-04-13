import { QARequest, QAWebSocketMessage } from '../types/qa';
import { FetchNewsRequest, NewsWebSocketMessage } from '../types/news';

// 从环境变量读取 WebSocket 基础 URL
const WS_BASE_URL = import.meta.env.VITE_WS_BASE_URL || 'ws://127.0.0.1:8000/ws';
console.log('WebSocket Base URL:', WS_BASE_URL); // Add console log for debugging


export class WebSocketClient {
    private ws: WebSocket | null = null;
    private url: string;
    private reconnectAttempts = 0;
    private maxReconnectAttempts = 5;
    private reconnectTimeout: number = 1000; // milliseconds
    private messageHandlers: ((data: any) => void)[] = [];
    private errorHandlers: ((error: Event) => void)[] = []; // Added error handlers
    private closeHandlers: ((event: CloseEvent) => void)[] = []; // Added close handlers

    constructor(path: string) {
        this.url = `<span class="math-inline">\{WS\_BASE\_URL\}</span>{path}`;
    }

    connect(): Promise<void> {
        // Prevent multiple connection attempts simultaneously
        if (this.ws && (this.ws.readyState === WebSocket.OPEN || this.ws.readyState === WebSocket.CONNECTING)) {
            console.warn('WebSocket already connected or connecting.');
            return Promise.resolve();
        }

        return new Promise((resolve, reject) => {
            console.log(`Attempting to connect to WebSocket: ${this.url}`);
            this.ws = new WebSocket(this.url);

            this.ws.onopen = () => {
                console.log(`WebSocket connected: ${this.url}`);
                this.reconnectAttempts = 0;
                resolve();
            };

            this.ws.onclose = (event) => {
                console.warn(`WebSocket closed: ${this.url}, Code: ${event.code}, Reason: ${event.reason}, Was Clean: ${event.wasClean}`);
                this.closeHandlers.forEach(handler => handler(event)); // Notify close handlers
                this.ws = null; // Clear the instance

                // Attempt to reconnect only if not a clean close (or based on specific codes)
                if (!event.wasClean && this.reconnectAttempts < this.maxReconnectAttempts) {
                    this.reconnectAttempts++;
                    const timeout = this.reconnectTimeout * (2 ** (this.reconnectAttempts - 1)); // Exponential backoff
                    console.log(`Attempting reconnect #${this.reconnectAttempts} in ${timeout}ms...`);
                    setTimeout(() => this.connect().catch(err => console.error("Reconnect failed:", err)), timeout);
                } else if (!event.wasClean) {
                    console.error(`Max reconnect attempts reached for ${this.url}.`);
                }
            };

            this.ws.onerror = (error) => {
                console.error(`WebSocket error: ${this.url}`, error);
                this.errorHandlers.forEach(handler => handler(error)); // Notify error handlers
                // Reject the initial connection promise on error
                // Note: reject might be called multiple times if reconnect fails repeatedly
                // Consider a mechanism to handle this if needed (e.g., only reject initial connect)
                if (this.reconnectAttempts === 0) { // Only reject on initial connect error
                    reject(error);
                }
            };

            this.ws.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data);
                    // console.debug('WebSocket message received:', data); // Can be noisy
                    this.messageHandlers.forEach(handler => handler(data));
                } catch (error) {
                    console.error('Failed to parse WebSocket message:', error, 'Data:', event.data);
                }
            };
        });
    }

    disconnect() {
        if (this.ws) {
            console.log(`Disconnecting WebSocket: ${this.url}`);
            // Prevent automatic reconnection attempts when explicitly disconnecting
            this.maxReconnectAttempts = 0;
            this.ws.close(1000, "Client requested disconnect"); // Use normal closure code
            this.ws = null;
        }
    }

    send(data: any) {
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            try {
                constjsonData = JSON.stringify(data);
                // console.debug('Sending WebSocket message:', jsonData); // Can be noisy
                this.ws.send(jsonData);
            } catch (error) {
                console.error('Failed to stringify or send WebSocket message:', error, 'Data:', data);
                throw new Error('Failed to send WebSocket message');
            }
        } else {
            console.error('WebSocket is not connected. Cannot send message.');
            throw new Error('WebSocket is not connected');
        }
    }

    onMessage(handler: (data: any) => void): () => void {
        this.messageHandlers.push(handler);
        // Return an unsubscribe function
        return () => {
            this.messageHandlers = this.messageHandlers.filter(h => h !== handler);
        };
    }

    onError(handler: (error: Event) => void): () => void {
        this.errorHandlers.push(handler);
        return () => {
            this.errorHandlers = this.errorHandlers.filter(h => h !== handler);
        };
    }

    onClose(handler: (event: CloseEvent) => void): () => void {
        this.closeHandlers.push(handler);
        return () => {
            this.closeHandlers = this.closeHandlers.filter(h => h !== handler);
        };
    }


    isConnected(): boolean {
        return this.ws !== null && this.ws.readyState === WebSocket.OPEN;
    }

    getReadyState(): number | null {
        return this.ws?.readyState ?? null;
    }
}

// --- QA WebSocket Client ---
export class QAWebSocketClient extends WebSocketClient {
    constructor() {
        super('/qa');
    }

    askQuestion(request: QARequest) {
        this.send({
            command: 'ask_question',
            data: request
        });
    }

    onMessage(handler: (data: QAWebSocketMessage) => void) {
        return super.onMessage(handler);
    }
}

// --- News WebSocket Client ---
export class NewsWebSocketClient extends WebSocketClient {
    constructor() {
        super('/news_progress'); // Path matches backend definition
    }

    // Note: Fetching news is triggered via HTTP POST, not WS command
    // This WS client is primarily for *receiving* progress updates

    // Method to trigger fetch (if needed via WS, though not current design)
    // fetchNews(request: FetchNewsRequest) {
    //     this.send({
    //         command: 'fetch_news', // This command might not exist on backend
    //         data: request
    //     });
    // }

    // Subscribe to messages broadcasted by the backend during fetch
    onMessage(handler: (data: NewsWebSocketMessage) => void) {
        return super.onMessage(handler);
    }
}
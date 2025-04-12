import { QARequest, QAWebSocketMessage } from '../types/qa';
import { FetchNewsRequest, NewsWebSocketMessage } from '../types/news';

const WS_BASE_URL = 'ws://127.0.0.1:8000/ws';

export class WebSocketClient {
    private ws: WebSocket | null = null;
    private url: string;
    private reconnectAttempts = 0;
    private maxReconnectAttempts = 5;
    private reconnectTimeout: number = 1000;
    private messageHandlers: ((data: any) => void)[] = [];

    constructor(path: string) {
        this.url = `${WS_BASE_URL}${path}`;
    }

    connect(): Promise<void> {
        return new Promise((resolve, reject) => {
            this.ws = new WebSocket(this.url);

            this.ws.onopen = () => {
                this.reconnectAttempts = 0;
                resolve();
            };

            this.ws.onclose = (event) => {
                if (this.reconnectAttempts < this.maxReconnectAttempts) {
                    this.reconnectAttempts++;
                    setTimeout(() => this.connect(), this.reconnectTimeout);
                }
            };

            this.ws.onerror = (error) => {
                reject(error);
            };

            this.ws.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data);
                    this.messageHandlers.forEach(handler => handler(data));
                } catch (error) {
                    console.error('Failed to parse WebSocket message:', error);
                }
            };
        });
    }

    disconnect() {
        if (this.ws) {
            this.ws.close();
            this.ws = null;
        }
    }

    send(data: any) {
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            this.ws.send(JSON.stringify(data));
        } else {
            throw new Error('WebSocket is not connected');
        }
    }

    onMessage(handler: (data: any) => void) {
        this.messageHandlers.push(handler);
        return () => {
            this.messageHandlers = this.messageHandlers.filter(h => h !== handler);
        };
    }

    isConnected(): boolean {
        return this.ws !== null && this.ws.readyState === WebSocket.OPEN;
    }
}

// QA WebSocket Client
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

// News WebSocket Client
export class NewsWebSocketClient extends WebSocketClient {
    constructor() {
        super('/news');
    }

    fetchNews(request: FetchNewsRequest) {
        this.send({
            command: 'fetch_news',
            data: request
        });
    }

    onMessage(handler: (data: NewsWebSocketMessage) => void) {
        return super.onMessage(handler);
    }
} 
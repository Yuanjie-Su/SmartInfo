import { create } from 'zustand';
import { QAHistoryItem, QAProgressUpdate } from '../types/qa';
import { qaApi } from '../services/api';

interface Message {
    id: string;
    type: 'user' | 'assistant';
    content: string;
    timestamp: Date;
    isStreaming?: boolean;
}

interface QAState {
    history: QAHistoryItem[];
    isLoading: boolean;
    error: string | null;
    messages: Message[];
    currentQuestion: string;
    isAnswering: boolean;
    currentAnswer: string;

    // Actions
    fetchHistory: () => Promise<void>;
    setCurrentQuestion: (question: string) => void;
    addUserMessage: (content: string) => void;
    startAssistantResponse: () => void;
    updateAssistantResponse: (content: string) => void;
    completeAssistantResponse: () => void;
    resetCurrentAnswer: () => void;
    clearMessages: () => void;
}

export const useQAStore = create<QAState>((set, get) => ({
    history: [],
    isLoading: false,
    error: null,
    messages: [],
    currentQuestion: '',
    isAnswering: false,
    currentAnswer: '',

    // Actions
    fetchHistory: async () => {
        try {
            set({ isLoading: true, error: null });
            const history = await qaApi.getQAHistory();
            set({ history, isLoading: false });
        } catch (error) {
            set({
                error: error instanceof Error ? error.message : '获取问答历史失败',
                isLoading: false
            });
        }
    },

    setCurrentQuestion: (question) => set({ currentQuestion: question }),

    addUserMessage: (content) => {
        const message: Message = {
            id: Date.now().toString(),
            type: 'user',
            content,
            timestamp: new Date()
        };

        set((state) => ({
            messages: [...state.messages, message],
            currentQuestion: ''
        }));
    },

    startAssistantResponse: () => {
        const message: Message = {
            id: Date.now().toString(),
            type: 'assistant',
            content: '',
            timestamp: new Date(),
            isStreaming: true
        };

        set((state) => ({
            messages: [...state.messages, message],
            isAnswering: true,
            currentAnswer: ''
        }));
    },

    updateAssistantResponse: (content) => {
        // 更新当前回答的内容
        set({ currentAnswer: content });

        // 更新消息列表中最后一条助手消息
        set((state) => {
            const messages = [...state.messages];
            const lastIndex = messages.length - 1;

            if (lastIndex >= 0 && messages[lastIndex].type === 'assistant') {
                messages[lastIndex] = {
                    ...messages[lastIndex],
                    content
                };
            }

            return { messages };
        });
    },

    completeAssistantResponse: () => {
        // 标记最后一条助手消息为完成状态
        set((state) => {
            const messages = [...state.messages];
            const lastIndex = messages.length - 1;

            if (lastIndex >= 0 && messages[lastIndex].type === 'assistant') {
                messages[lastIndex] = {
                    ...messages[lastIndex],
                    isStreaming: false
                };
            }

            return {
                messages,
                isAnswering: false
            };
        });
    },

    resetCurrentAnswer: () => set({ currentAnswer: '' }),

    clearMessages: () => set({ messages: [] })
})); 
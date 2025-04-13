// temp/frontend/src/store/newsStore.ts
import { create } from 'zustand';
// Use updated types
import { NewsItem, NewsCategory, NewsSource, NewsProgressUpdate, StreamChunkUpdate } from '../types/news';
import { newsApi } from '../services/api';

interface NewsState {
    items: NewsItem[];
    isLoading: boolean;
    error: string | null;
    selectedItem: NewsItem | null;
    categories: NewsCategory[]; // Store full category objects
    sources: NewsSource[];     // Store full source objects
    selectedCategory: number | null; // Use ID for filtering
    selectedSource: number | null;   // Use ID for filtering
    searchQuery: string;

    // Pagination state
    currentPage: number;
    pageSize: number;
    // totalItems: number | null; // Backend doesn't easily provide total count yet

    // Fetch news progress modal state
    isProgressModalOpen: boolean;
    fetchProgress: NewsProgressUpdate[]; // Store multiple progress updates
    fetchStreamChunks: string[]; // Store stream chunks

    // Actions
    fetchNewsItems: (page?: number, limit?: number) => Promise<void>;
    fetchCategories: () => Promise<void>;
    fetchSources: () => Promise<void>;
    selectItem: (item: NewsItem | null) => void;
    setSelectedCategory: (categoryId: number | null) => void;
    setSelectedSource: (sourceId: number | null) => void;
    setSearchQuery: (query: string) => void;
    triggerFetchNews: (sourceIds?: number[]) => Promise<void>; // Action to start fetch

    // Progress modal actions
    openProgressModal: () => void;
    closeProgressModal: () => void;
    addProgressUpdate: (data: NewsProgressUpdate) => void;
    addStreamChunk: (chunk: string) => void;
    clearFetchProgress: () => void;
}

export const useNewsStore = create<NewsState>((set, get) => ({
    items: [],
    isLoading: false,
    error: null,
    selectedItem: null,
    categories: [],
    sources: [],
    selectedCategory: null,
    selectedSource: null,
    searchQuery: '',

    // Pagination state
    currentPage: 1,
    pageSize: 50, // Default page size
    // totalItems: null,

    // Fetch news progress state
    isProgressModalOpen: false,
    fetchProgress: [],
    fetchStreamChunks: [],

    // --- Actions ---

    // Fetch News Items for Display
    fetchNewsItems: async (page: number = 1, limit?: number) => {
        set({ isLoading: true, error: null });
        const effectiveLimit = limit ?? get().pageSize;
        const offset = (page - 1) * effectiveLimit;
        try {
            // TODO: Add filtering based on get().selectedCategory / get().selectedSource if backend supports it
            // Currently, the backend GET /items doesn't support filtering by category/source/search
            // We will fetch all and rely on frontend filtering for now, or update backend later.
            const items = await newsApi.getNewsItems(effectiveLimit, offset);
            set({
                items,
                isLoading: false,
                currentPage: page,
                // Update totalItems if API provided it
            });
        } catch (error) {
            const message = error instanceof Error ? error.message : '获取新闻列表失败';
            console.error("fetchNewsItems error:", error);
            set({ error: message, isLoading: false, items: [] }); // Clear items on error
        }
    },

    // Fetch Categories for Filtering Dropdowns, etc.
    fetchCategories: async () => {
        // No loading state needed if it's just for filters in background
        try {
            const categories = await newsApi.getCategories();
            set({ categories });
        } catch (error) {
            const message = error instanceof Error ? error.message : '获取分类失败';
            console.error("fetchCategories error:", error);
            set({ error: message }); // Set error state
        }
    },

    // Fetch Sources for Filtering Dropdowns, etc.
    fetchSources: async () => {
        try {
            const sources = await newsApi.getSources();
            set({ sources });
        } catch (error) {
            const message = error instanceof Error ? error.message : '获取来源失败';
            console.error("fetchSources error:", error);
            set({ error: message }); // Set error state
        }
    },

    selectItem: (item) => set({ selectedItem: item }),

    setSelectedCategory: (categoryId) => {
        set({ selectedCategory: categoryId, currentPage: 1 }); // Reset page when filter changes
        // get().fetchNewsItems(); // Optionally re-fetch immediately
    },

    setSelectedSource: (sourceId) => {
        set({ selectedSource: sourceId, currentPage: 1 }); // Reset page when filter changes
        // get().fetchNewsItems(); // Optionally re-fetch immediately
    },

    setSearchQuery: (query) => set({ searchQuery: query, currentPage: 1 }), // Reset page

    // Trigger the backend news fetch process
    triggerFetchNews: async (sourceIds?: number[]) => {
        set({ isProgressModalOpen: true, fetchProgress: [], fetchStreamChunks: [], error: null }); // Open modal and clear old data
        try {
            await newsApi.fetchNews({ source_ids: sourceIds });
            // Success is indicated by the API returning 202 and WS messages starting
            // No need to set loading false here, WS messages will indicate progress/completion
        } catch (error) {
            const message = error instanceof Error ? error.message : '启动新闻抓取失败';
            console.error("triggerFetchNews error:", error);
            set({ error: message, isProgressModalOpen: false }); // Close modal on trigger error
        }
    },


    // --- Progress Modal Actions ---
    openProgressModal: () => set({
        isProgressModalOpen: true,
        fetchProgress: [],
        fetchStreamChunks: [],
        error: null, // Clear previous errors
    }),

    closeProgressModal: () => set({ isProgressModalOpen: false }),

    addProgressUpdate: (data) => set((state) => ({
        fetchProgress: [...state.fetchProgress, data] // Append new progress update
    })),

    addStreamChunk: (chunk) => set((state) => ({
        fetchStreamChunks: [...state.fetchStreamChunks, chunk]
    })),

    clearFetchProgress: () => set({
        fetchProgress: [],
        fetchStreamChunks: []
    }),
}));
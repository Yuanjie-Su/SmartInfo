import { create } from 'zustand';
import { NewsItem, NewsProgressUpdate, NewsAnalysisChunk } from '../types/news';
import { newsApi } from '../services/api';

interface NewsState {
    items: NewsItem[];
    isLoading: boolean;
    error: string | null;
    selectedItem: NewsItem | null;
    categories: string[];
    sources: string[];
    selectedCategory: string;
    selectedSource: string;
    searchQuery: string;

    // Fetch news progress modal state
    isProgressModalOpen: boolean;
    progressData: NewsProgressUpdate | null;
    analysisChunks: NewsAnalysisChunk[];

    // Actions
    fetchNewsItems: (category?: string, source?: string, search?: string) => Promise<void>;
    fetchCategories: () => Promise<void>;
    fetchSources: () => Promise<void>;
    selectItem: (item: NewsItem | null) => void;
    setSelectedCategory: (category: string) => void;
    setSelectedSource: (source: string) => void;
    setSearchQuery: (query: string) => void;

    // Progress modal actions
    openProgressModal: () => void;
    closeProgressModal: () => void;
    updateProgress: (data: NewsProgressUpdate) => void;
    addAnalysisChunk: (chunk: NewsAnalysisChunk) => void;
    clearProgress: () => void;
}

export const useNewsStore = create<NewsState>((set, get) => ({
    items: [],
    isLoading: false,
    error: null,
    selectedItem: null,
    categories: [],
    sources: [],
    selectedCategory: '',
    selectedSource: '',
    searchQuery: '',

    // Fetch news progress state
    isProgressModalOpen: false,
    progressData: null,
    analysisChunks: [],

    // Actions
    fetchNewsItems: async (category?: string, source?: string, search?: string) => {
        try {
            set({ isLoading: true, error: null });
            const items = await newsApi.getNewsItems(
                category || get().selectedCategory,
                source || get().selectedSource,
                search || get().searchQuery
            );
            set({ items, isLoading: false });
        } catch (error) {
            set({
                error: error instanceof Error ? error.message : '获取新闻失败',
                isLoading: false
            });
        }
    },

    fetchCategories: async () => {
        try {
            const categories = await newsApi.getNewsCategories();
            set({ categories });
        } catch (error) {
            set({ error: error instanceof Error ? error.message : '获取分类失败' });
        }
    },

    fetchSources: async () => {
        try {
            const sources = await newsApi.getNewsSources();
            set({ sources });
        } catch (error) {
            set({ error: error instanceof Error ? error.message : '获取来源失败' });
        }
    },

    selectItem: (item) => set({ selectedItem: item }),

    setSelectedCategory: (category) => set({ selectedCategory: category }),

    setSelectedSource: (source) => set({ selectedSource: source }),

    setSearchQuery: (query) => set({ searchQuery: query }),

    // Progress modal actions
    openProgressModal: () => set({
        isProgressModalOpen: true,
        progressData: null,
        analysisChunks: []
    }),

    closeProgressModal: () => set({ isProgressModalOpen: false }),

    updateProgress: (data) => set({ progressData: data }),

    addAnalysisChunk: (chunk) => set((state) => ({
        analysisChunks: [...state.analysisChunks, chunk]
    })),

    clearProgress: () => set({
        progressData: null,
        analysisChunks: []
    })
})); 
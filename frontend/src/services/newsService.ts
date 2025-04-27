import api from './api';
import {
  News,
  NewsCategory,
  NewsCreate,
  NewsFilterParams,
  NewsSource,
  NewsSourceCreate,
  NewsCategoryCreate,
  NewsAnalysisRequest
} from '../utils/types';

const BASE_PATH = '/news';

// News Categories API
export const getCategories = async (): Promise<NewsCategory[]> => {
  const response = await api.get(`${BASE_PATH}/categories`);
  return response.data;
};

export const createCategory = async (category: NewsCategoryCreate): Promise<NewsCategory> => {
  const response = await api.post(`${BASE_PATH}/categories`, category);
  return response.data;
};

export const updateCategory = async (id: number, category: NewsCategoryCreate): Promise<NewsCategory> => {
  const response = await api.put(`${BASE_PATH}/categories/${id}`, category);
  return response.data;
};

export const deleteCategory = async (id: number): Promise<void> => {
  await api.delete(`${BASE_PATH}/categories/${id}`);
};

// News Sources API
export const getSources = async (categoryId?: number): Promise<NewsSource[]> => {
  const params = categoryId ? { category_id: categoryId } : {};
  const response = await api.get(`${BASE_PATH}/sources`, { params });
  return response.data;
};

export const createSource = async (source: NewsSourceCreate): Promise<NewsSource> => {
  const response = await api.post(`${BASE_PATH}/sources`, source);
  return response.data;
};

export const updateSource = async (id: number, source: NewsSourceCreate): Promise<NewsSource> => {
  const response = await api.put(`${BASE_PATH}/sources/${id}`, source);
  return response.data;
};

export const deleteSource = async (id: number): Promise<void> => {
  await api.delete(`${BASE_PATH}/sources/${id}`);
};

// News Articles API
export const getNews = async (params: NewsFilterParams): Promise<News[]> => {
  const response = await api.get(`${BASE_PATH}/articles`, { params });
  return response.data;
};

export const getNewsById = async (id: number): Promise<News> => {
  const response = await api.get(`${BASE_PATH}/articles/${id}`);
  return response.data;
};

export const createNews = async (news: NewsCreate): Promise<News> => {
  const response = await api.post(`${BASE_PATH}/articles`, news);
  return response.data;
};

export const updateNews = async (id: number, news: NewsCreate): Promise<News> => {
  const response = await api.put(`${BASE_PATH}/articles/${id}`, news);
  return response.data;
};

export const deleteNews = async (id: number): Promise<void> => {
  await api.delete(`${BASE_PATH}/articles/${id}`);
};

// News Analysis API
export const analyzeNews = async (request: NewsAnalysisRequest): Promise<{ message: string; task_id: string }> => {
  const response = await api.post(`${BASE_PATH}/analyze`, request);
  return response.data;
};

// News Fetch API
export const fetchNews = async (sourceId?: number, fetchAll: boolean = false): Promise<{ message: string; task_id: string }> => {
  const params = {
    source_id: sourceId,
    fetch_all: fetchAll
  };
  const response = await api.post(`${BASE_PATH}/fetch`, null, { params });
  return response.data;
}; 
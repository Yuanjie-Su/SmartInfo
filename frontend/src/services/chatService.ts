import api from './api';
import {
  Chat,
  ChatCreate,
  Message,
  MessageCreate,
  Question,
  ChatAnswer
} from '../utils/types';

const BASE_PATH = '/api/chat';

// Chat Sessions API
export const getChats = async (): Promise<Chat[]> => {
  const response = await api.get(`${BASE_PATH}/`);
  return response.data;
};

export const createChat = async (chat: ChatCreate): Promise<Chat> => {
  const response = await api.post(`${BASE_PATH}/`, chat);
  return response.data;
};

export const getChat = async (chatId: number): Promise<Chat> => {
  const response = await api.get(`${BASE_PATH}/${chatId}`);
  return response.data;
};

export const updateChat = async (chatId: number, chat: ChatCreate): Promise<Chat> => {
  const response = await api.put(`${BASE_PATH}/${chatId}`, chat);
  return response.data;
};

export const deleteChat = async (chatId: number): Promise<void> => {
  await api.delete(`${BASE_PATH}/${chatId}`);
};

// Chat Messages API
export const getMessages = async (chatId: number): Promise<Message[]> => {
  const response = await api.get(`${BASE_PATH}/${chatId}/messages`);
  return response.data;
};

export const createMessage = async (message: MessageCreate): Promise<Message> => {
  const response = await api.post(`${BASE_PATH}/messages`, message);
  return response.data;
};

export const getMessage = async (messageId: number): Promise<Message> => {
  const response = await api.get(`${BASE_PATH}/messages/${messageId}`);
  return response.data;
};

export const deleteMessage = async (messageId: number): Promise<void> => {
  await api.delete(`${BASE_PATH}/messages/${messageId}`);
};

// LLM Question/Answer API
export const askQuestion = async (question: Question): Promise<ChatAnswer> => {
  const response = await api.post(`${BASE_PATH}/ask`, question);
  return response.data;
}; 
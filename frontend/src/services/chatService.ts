import api from './api';
import axios from 'axios'; // Import axios for error checking
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

export const getChat = async (chatId: number): Promise<Chat | null> => {
  try {
    const response = await api.get<Chat>(`${BASE_PATH}/${chatId}`);
    return response.data;
  } catch (error) {
    if (axios.isAxiosError(error) && error.response?.status === 404) {
      console.warn(`ChatService: Chat with ID ${chatId} not found (404).`);
      return null; // Return null for not found
    }
    // Re-throw other errors (network, 5xx, etc.)
    console.error(`ChatService: Error fetching chat ${chatId}:`, error);
    throw error;
  }
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

export const getMessage = async (messageId: number): Promise<Message | null> => {
  try {
    const response = await api.get<Message>(`${BASE_PATH}/messages/${messageId}`);
    return response.data;
  } catch (error) {
    if (axios.isAxiosError(error) && error.response?.status === 404) {
      console.warn(`ChatService: Message with ID ${messageId} not found (404).`);
      return null; // Return null for not found
    }
    // Re-throw other errors (network, 5xx, etc.)
    console.error(`ChatService: Error fetching message ${messageId}:`, error);
    throw error;
  }
};

export const deleteMessage = async (messageId: number): Promise<void> => {
  await api.delete(`${BASE_PATH}/messages/${messageId}`);
};

// LLM Question/Answer API
export const askQuestion = async (question: Question): Promise<ChatAnswer> => {
  const response = await api.post(`${BASE_PATH}/ask`, question);
  return response.data;
};

import React, { useState, useEffect, useRef } from 'react';
import { useRouter } from 'next/router';
import {
  Layout,
  List,
  Input,
  Button,
  Avatar,
  Spin,
  Empty, // Import Empty
  Typography,
  Space,
  Card,
  message,
  Alert, // Import Alert
  Tooltip
} from 'antd';
import {
  UserOutlined,
  RobotOutlined,
  SendOutlined,
  CopyOutlined
} from '@ant-design/icons';

import * as chatService from '@/services/chatService';
import { handleApiError, extractErrorMessage } from '@/utils/apiErrorHandler'; // Import extractErrorMessage
import { Chat, Message, Question } from '@/utils/types';
import withAuth from '@/components/auth/withAuth'; // Import the HOC

const { Content } = Layout;
const { Title, Text, Paragraph } = Typography;
const { TextArea } = Input;

const ChatPageInternal: React.FC = () => {
  // State
  const [chats, setChats] = useState<Chat[]>([]);
  const [selectedChatId, setSelectedChatId] = useState<number | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [inputMessage, setInputMessage] = useState('');
  const [loadingChats, setLoadingChats] = useState(true);
  const [loadingMessages, setLoadingMessages] = useState(false);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<{ type: string, message: string, status?: number } | null>(null); // Updated error state type

  // Refs
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const messageListRef = useRef<HTMLDivElement>(null);
  const router = useRouter();

  // Load chat sessions on component mount
  useEffect(() => {
    fetchChats();
  }, []);

  // Load messages when selected chat changes
  useEffect(() => {
    if (selectedChatId) {
      fetchMessages(selectedChatId);
    } else {
      setMessages([]);
    }
  }, [selectedChatId]);

  // Auto-scroll to bottom when messages change
  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  // Fetch all chat sessions
  const fetchChats = async () => {
    try {
      setLoadingChats(true);
      setError(null); // Reset error state
      const response = await chatService.getChats();
      setChats(response);

      // Select first chat if available and none is selected
      if (response.length > 0 && !selectedChatId) {
        setSelectedChatId(response[0].id);
      }
    } catch (err: any) { // Catch the error here
      console.error('Failed to fetch chats:', err);
      const errorDetails = extractErrorMessage(err); // Use the structured error handler
      setError(errorDetails); // Set the structured error state
      // No need for global message here
    } finally {
      setLoadingChats(false);
    }
  };

  // Fetch messages for a chat
  const fetchMessages = async (chatId: number) => {
    try {
      setLoadingMessages(true);
      setError(null); // Reset error state
      const response = await chatService.getMessages(chatId);
      setMessages(response);
    } catch (err: any) { // Catch the error here
      console.error('Failed to fetch messages:', err);
      const errorDetails = extractErrorMessage(err); // Use the structured error handler
      setError(errorDetails); // Set the structured error state
      // No need for global message here
    } finally {
      setLoadingMessages(false);
    }
  };

  // Send a message
  const handleSendMessage = async () => {
    if (!inputMessage.trim()) return;

    // If no chat is selected, create a new one first
    let chatId = selectedChatId;
    if (!chatId) {
      try {
        const newChat = await chatService.createChat({ title: '新聊天' });
        chatId = newChat.id;
        setSelectedChatId(chatId);
        await fetchChats(); // Refresh chat list
      } catch (error) {
        handleApiError(error, '创建新聊天失败');
        return;
      }
    }

    const userMessageObj: Message = {
      id: Date.now(), // Temporary ID for optimistic UI update
      chat_id: chatId,
      sender: 'user',
      content: inputMessage,
      timestamp: new Date().toISOString(), // Use ISO string
      sequence_number: messages.length + 1 // Temporary sequence number
    };

    try {
      setSending(true);

      // Optimistically add user message to UI
      setMessages(prev => [...prev, userMessageObj]);
      setInputMessage('');

      // Create user message in backend
      const userMessage = await chatService.createMessage({
        chat_id: chatId,
        sender: 'user',
        content: inputMessage
      });

      // Prepare and send question to LLM
      const question: Question = {
        chat_id: chatId,
        content: inputMessage
      };

      const answer = await chatService.askQuestion(question);

      // Add assistant response to UI
      const assistantMessageObj: Message = {
        id: answer.message_id || Date.now() + 1,
        chat_id: chatId,
        sender: 'assistant',
        content: answer.content,
        timestamp: new Date().toISOString(), // Use ISO string
        sequence_number: messages.length + 2 // Temporary sequence number (after user msg)
      };

      setMessages(prev => [...prev, assistantMessageObj]);

      // Refresh messages from server to ensure consistency
      await fetchMessages(chatId);
    } catch (error) {
      handleApiError(error, '发送消息失败');
    } finally {
      setSending(false);
    }
  };

  // Handle message input
  const handleInputChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInputMessage(e.target.value);
  };

  // Handle pressing Enter to send (except with Shift)
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage();
    }
  };

  // Copy message to clipboard
  const handleCopyMessage = (content: string) => {
    navigator.clipboard.writeText(content)
      .then(() => message.success('复制成功'))
      .catch(() => message.error('复制失败'));
  };

  // Scroll to bottom of message list
  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  return (
    // This div becomes the direct child of MainLayout's Content area
    // It should fill the height and manage its children with flexbox
    <div style={{
      height: '100%', // Fill the parent Content area from MainLayout
      display: 'flex',
      flexDirection: 'column',
      // The background, padding, and borderRadius are now applied here
      background: '#fff',
      padding: 24,
      borderRadius: 8,
    }}>
      {/* Messages Display - this was previously inside the AntD Content */}
      {error ? ( 
        error.type === 'notFound' ? (
          <Empty description={error.message || "Chat or messages not found."} style={{ margin: '60px 0' }} image={Empty.PRESENTED_IMAGE_SIMPLE} />
        ) : error.type === 'forbidden' ? (
          <Alert
            message="Access Denied"
            description={error.message || "You do not have permission to view this chat."}
            type="error"
            showIcon
            style={{ marginBottom: 16 }}
          />
        ) : (
          <Alert
            message="Error"
            description={error.message || "An unexpected error occurred."}
            type="error"
            showIcon
            style={{ marginBottom: 16 }}
          />
        )
      ) : (
        <div
          style={{
            flexGrow: 1,
            overflowY: 'auto',
            padding: '0 16px',
            marginBottom: 16,
            border: '1px solid #f0f0f0',
            borderRadius: 4
          }}
          ref={messageListRef}
        >
          {loadingMessages ? (
            <div style={{ display: 'flex', justifyContent: 'center', padding: '40px 0' }}>
              <Spin size="large" />
            </div>
          ) : messages.length === 0 ? (
            <Empty
              description="没有消息"
              style={{ margin: '60px 0' }}
              image={Empty.PRESENTED_IMAGE_SIMPLE}
            />
          ) : (
            <div style={{ padding: '16px 0' }}>
              {messages.map((msg) => {
                const isUser = msg.sender === 'user';
                return (
                  <div
                    key={msg.id}
                    style={{
                      display: 'flex',
                      justifyContent: isUser ? 'flex-end' : 'flex-start',
                      marginBottom: 16,
                    }}
                  >
                    <Card
                      className={isUser ? 'user-message-card' : 'assistant-message-card'}
                      style={{ maxWidth: '75%' }}
                      bodyStyle={{ padding: '10px 14px' }}
                    >
                      <Space align="start" size={8}>
                        {!isUser && (
                          <Avatar icon={<RobotOutlined />} style={{ backgroundColor: '#788596' }} />
                        )}
                        <div style={{ flex: 1 }}>
                          <Paragraph style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word', marginBottom: 4 }}>
                            {msg.content}
                          </Paragraph>
                          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                            <Text type="secondary" style={{ fontSize: '11px' }}>
                              {msg.timestamp ? new Date(msg.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : ''}
                            </Text>
                            <Tooltip title="Copy message">
                              <Button
                                type="text"
                                icon={<CopyOutlined />}
                                size="small"
                                onClick={() => handleCopyMessage(msg.content)}
                                style={{color: 'var(--text-secondary)', padding: '0 4px'}}
                              />
                            </Tooltip>
                          </div>
                        </div>
                        {isUser && (
                          <Avatar icon={<UserOutlined />} style={{ backgroundColor: 'var(--accent-color)' }} />
                        )}
                      </Space>
                    </Card>
                  </div>
                );
              })}
              <div ref={messagesEndRef} />
            </div>
          )}
        </div>
      )}

      {/* Message Input - this was previously inside the AntD Content */}
      <div style={{ display: 'flex', alignItems: 'flex-end' }}>
        <TextArea
          value={inputMessage}
          onChange={handleInputChange}
          onKeyDown={handleKeyDown}
          placeholder="输入消息..."
          autoSize={{ minRows: 2, maxRows: 6 }}
          style={{ flex: 1, marginRight: 8 }}
          disabled={sending}
        />
        <Button
          type="primary"
          icon={<SendOutlined />}
          onClick={handleSendMessage}
          loading={sending}
          disabled={!inputMessage.trim()}
          style={{ height: 'auto', padding: '8px 16px' }}
        >
          发送
        </Button>
      </div>
    </div>
  );
};

// Wrap the internal component with the HOC for authentication
const ChatPage = withAuth(ChatPageInternal);
export default ChatPage;

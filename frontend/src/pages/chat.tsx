import React, { useState, useEffect, useRef } from 'react';
import { useRouter } from 'next/router';
import { 
  Layout, 
  List, 
  Input, 
  Button, 
  Avatar, 
  Spin, 
  Empty, 
  Select, 
  Typography,
  Space,
  Card,
  message
} from 'antd';
import { 
  UserOutlined, 
  RobotOutlined, 
  SendOutlined, 
  PlusOutlined,
  CopyOutlined 
} from '@ant-design/icons';
import MainLayout from '@/components/layout/MainLayout';
import * as chatService from '@/services/chatService';
import { handleApiError } from '@/utils/apiErrorHandler';
import { Chat, Message, ChatQuestion } from '@/utils/types';

const { Content } = Layout;
const { Title, Text, Paragraph } = Typography;
const { TextArea } = Input;
const { Option } = Select;

const ChatPage: React.FC = () => {
  // State
  const [chats, setChats] = useState<Chat[]>([]);
  const [selectedChatId, setSelectedChatId] = useState<number | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [inputMessage, setInputMessage] = useState('');
  const [loadingChats, setLoadingChats] = useState(true);
  const [loadingMessages, setLoadingMessages] = useState(false);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);

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
      const response = await chatService.getChats();
      setChats(response);
      
      // Select first chat if available and none is selected
      if (response.length > 0 && !selectedChatId) {
        setSelectedChatId(response[0].id);
      }
    } catch (error) {
      handleApiError(error, '获取聊天会话失败');
      setError('加载聊天会话时出错');
    } finally {
      setLoadingChats(false);
    }
  };

  // Fetch messages for a chat
  const fetchMessages = async (chatId: number) => {
    try {
      setLoadingMessages(true);
      const response = await chatService.getMessages(chatId);
      setMessages(response);
    } catch (error) {
      handleApiError(error, '获取消息失败');
      setError('加载消息时出错');
    } finally {
      setLoadingMessages(false);
    }
  };

  // Create a new chat
  const handleNewChat = async () => {
    try {
      const newChat = await chatService.createChat({ title: '新聊天' });
      await fetchChats(); // Refresh chat list
      setSelectedChatId(newChat.id);
      setMessages([]);
      setInputMessage('');
    } catch (error) {
      handleApiError(error, '创建新聊天失败');
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
      timestamp: Date.now()
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
      const question: ChatQuestion = {
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
        timestamp: Date.now()
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

  // Go to detailed chat page
  const handleGoToChat = (chatId: number) => {
    router.push(`/chat/${chatId}`);
  };

  return (
    <MainLayout>
      <Layout style={{ padding: '24px', height: 'calc(100vh - 64px)' }}>
        <Content style={{ 
          background: '#fff', 
          padding: 24, 
          margin: 0, 
          borderRadius: 8,
          height: '100%',
          display: 'flex',
          flexDirection: 'column'
        }}>
          {/* Chat Selection Header */}
          <div style={{ marginBottom: 16, display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <Space>
              <Select
                style={{ width: 300 }}
                placeholder="选择聊天会话"
                loading={loadingChats}
                value={selectedChatId}
                onChange={setSelectedChatId}
                dropdownRender={menu => (
                  <>
                    {menu}
                    <div style={{ padding: '8px', display: 'flex', justifyContent: 'space-between' }}>
                      <Button
                        type="primary"
                        icon={<PlusOutlined />}
                        onClick={handleNewChat}
                      >
                        新聊天
                      </Button>
                    </div>
                  </>
                )}
              >
                {chats.map((chat) => (
                  <Option key={chat.id} value={chat.id}>
                    {chat.title}
                  </Option>
                ))}
              </Select>
              <Button 
                type="primary" 
                icon={<PlusOutlined />} 
                onClick={handleNewChat}
              >
                新聊天
              </Button>
            </Space>
            
            {selectedChatId && (
              <Button
                type="link"
                onClick={() => handleGoToChat(selectedChatId)}
              >
                查看详情
              </Button>
            )}
          </div>

          {/* Messages Display */}
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
                        style={{
                          maxWidth: '70%',
                          backgroundColor: isUser ? '#f0f2ff' : '#fff',
                          borderColor: isUser ? '#d7d9e6' : '#e0e0e0',
                        }}
                        bodyStyle={{ padding: '12px 16px' }}
                      >
                        <div style={{ display: 'flex', alignItems: 'flex-start' }}>
                          <Avatar 
                            icon={isUser ? <UserOutlined /> : <RobotOutlined />} 
                            style={{ 
                              marginRight: 8, 
                              backgroundColor: isUser ? '#1677ff' : '#52c41a' 
                            }}
                          />
                          <div style={{ flex: 1 }}>
                            <div
                              style={{
                                whiteSpace: 'pre-wrap',
                                wordBreak: 'break-word',
                              }}
                            >
                              {msg.content}
                            </div>
                            <div style={{ 
                              marginTop: 8, 
                              display: 'flex', 
                              justifyContent: 'space-between',
                              alignItems: 'center'
                            }}>
                              <Text type="secondary" style={{ fontSize: '0.8rem' }}>
                                {msg.timestamp ? new Date(msg.timestamp).toLocaleTimeString() : ''}
                              </Text>
                              
                              <Button 
                                type="text" 
                                icon={<CopyOutlined />} 
                                size="small"
                                onClick={() => handleCopyMessage(msg.content)}
                                title="复制消息"
                              />
                            </div>
                          </div>
                        </div>
                      </Card>
                    </div>
                  );
                })}
                <div ref={messagesEndRef} />
              </div>
            )}
          </div>

          {/* Message Input */}
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
        </Content>
      </Layout>
    </MainLayout>
  );
};

export default ChatPage; 
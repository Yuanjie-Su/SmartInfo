import React, { useState, useEffect, useRef } from 'react';
import { useRouter } from 'next/router';
import { 
  Typography, 
  Input, 
  Button, 
  Card, 
  Avatar, 
  message, 
  Spin,
  Divider,
  Space
} from 'antd';
import { 
  SendOutlined, 
  UserOutlined, 
  RobotOutlined,
  CopyOutlined,
  EditOutlined
} from '@ant-design/icons';
import { Chat, Message, MessageCreate } from '@/utils/types';
import * as chatService from '@/services/chatService';

const { Title, Text, Paragraph } = Typography;
const { TextArea } = Input;

const ChatPage: React.FC = () => {
  const router = useRouter();
  const { id } = router.query;
  const [chat, setChat] = useState<Chat | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [newMessage, setNewMessage] = useState('');
  
  // Refs
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textAreaRef = useRef<any>(null);
  
  // Load chat data when id changes
  useEffect(() => {
    if (id) {
      loadChat(parseInt(id as string));
    }
  }, [id]);
  
  // Scroll to bottom when messages change
  useEffect(() => {
    scrollToBottom();
  }, [messages]);
  
  const loadChat = async (chatId: number) => {
    try {
      setLoading(true);
      const chatData = await chatService.getChat(chatId);
      setChat(chatData);
      
      // Load messages for this chat
      const messagesData = await chatService.getMessages(chatId);
      setMessages(messagesData);
    } catch (error) {
      console.error('Failed to load chat:', error);
      message.error('Failed to load chat data');
    } finally {
      setLoading(false);
    }
  };
  
  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };
  
  const handleSendMessage = async () => {
    if (!newMessage.trim() || !chat) return;
    
    const userMessageData: MessageCreate = {
      chat_id: chat.id,
      sender: 'user',
      content: newMessage
    };
    
    try {
      setSending(true);
      
      // Create user message
      const userMessage = await chatService.createMessage(userMessageData);
      setMessages(prev => [...prev, userMessage]);
      setNewMessage('');
      
      // Focus back on the textarea
      if (textAreaRef.current) {
        textAreaRef.current.focus();
      }
      
      // Now ask the question and get answer
      const response = await chatService.askQuestion({
        chat_id: chat.id,
        content: newMessage,
      });
      
      // If no message_id in response, create new assistant message
      if (!response.message_id) {
        const assistantMessageData: MessageCreate = {
          chat_id: chat.id,
          sender: 'assistant',
          content: response.content
        };
        const assistantMessage = await chatService.createMessage(assistantMessageData);
        setMessages(prev => [...prev, assistantMessage]);
      } else {
        // Otherwise, update messages to include the new message
        loadChat(chat.id);
      }
    } catch (error) {
      console.error('Failed to send message:', error);
      message.error('Failed to send message');
    } finally {
      setSending(false);
    }
  };
  
  const handleCopyMessage = (content: string) => {
    if (navigator.clipboard && window.isSecureContext) {
      navigator.clipboard.writeText(content)
        .then(() => message.success('Copied to clipboard'))
        .catch(() => message.error('Failed to copy message'));
    } else {
      message.error('Clipboard functionality is not available in this browser or context');
    }
  };
  
  const renderMessages = () => {
    return messages.map((msg) => {
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
                style={{ marginRight: 8, backgroundColor: isUser ? '#1677ff' : '#52c41a' }}
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
                  
                  <Space>
                    <Button 
                      type="text" 
                      icon={<CopyOutlined />} 
                      size="small"
                      onClick={() => handleCopyMessage(msg.content)}
                      title="Copy message"
                    />
                  </Space>
                </div>
              </div>
            </div>
          </Card>
        </div>
      );
    });
  };
  
  if (loading) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '50vh' }}>
        <Spin size="large" />
      </div>
    );
  }
  
  if (!chat) {
    return (
      <div style={{ textAlign: 'center', marginTop: 50 }}>
        <Title level={3}>Chat not found</Title>
        <Paragraph>The requested chat could not be found or has been deleted.</Paragraph>
        <Button type="primary" onClick={() => router.push('/')}>
          Return to Home
        </Button>
      </div>
    );
  }
  
  return (
    <div style={{ height: 'calc(100vh - 150px)', display: 'flex', flexDirection: 'column' }}>
      <div style={{ marginBottom: 16 }}>
        <Title level={3}>{chat.title}</Title>
      </div>
      
      <Divider style={{ margin: '0 0 16px 0' }} />
      
      <div style={{ flex: 1, overflowY: 'auto', padding: '0 4px' }}>
        {messages.length === 0 ? (
          <div style={{ textAlign: 'center', marginTop: 40 }}>
            <Title level={4}>Start a conversation</Title>
            <Paragraph>Ask a question or start a conversation with the AI assistant.</Paragraph>
          </div>
        ) : (
          renderMessages()
        )}
        <div ref={messagesEndRef} />
      </div>
      
      <div style={{ padding: '16px 0' }}>
        <div style={{ display: 'flex' }}>
          <TextArea
            ref={textAreaRef}
            value={newMessage}
            onChange={(e) => setNewMessage(e.target.value)}
            placeholder="Type your message here..."
            autoSize={{ minRows: 2, maxRows: 6 }}
            disabled={sending}
            onPressEnter={(e) => {
              if (!e.shiftKey) {
                e.preventDefault();
                handleSendMessage();
              }
            }}
            style={{ flex: 1, borderRadius: '4px 0 0 4px' }}
          />
          <Button
            type="primary"
            icon={<SendOutlined />}
            onClick={handleSendMessage}
            loading={sending}
            style={{ height: 'auto', borderRadius: '0 4px 4px 0' }}
          />
        </div>
        <Text type="secondary" style={{ fontSize: '12px', marginTop: 4 }}>
          Press Enter to send, Shift+Enter for new line
        </Text>
      </div>
    </div>
  );
};

export default ChatPage;

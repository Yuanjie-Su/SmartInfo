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
  Space,
  Tooltip
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
import { extractErrorMessage } from '@/utils/apiErrorHandler'; // Import extractErrorMessage
import withAuth from '@/components/auth/withAuth'; // Import the HOC

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
  const [error, setError] = useState<{ type: string, message: string, status?: number } | null>(null); // Updated error state type
  
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
      setError(null); // Reset error state
      const chatData = await chatService.getChat(chatId); // This service method now returns null for 404

      if (chatData === null) { // Handle not found specifically (service returned null)
        setChat(null); // Ensure chat state is null
        setMessages([]); // Clear messages
        // Set a specific notFound error type
        setError({ type: 'notFound', message: `Chat session with ID ${chatId} not found or not owned by user.`, status: 404 });
        return; // Stop processing
      }

      setChat(chatData);

      // Load messages for this chat (assuming getMessages also handles errors and returns [])
      const messagesData = await chatService.getMessages(chatId);
      setMessages(messagesData);

    } catch (err: any) { // Catch other errors (network, 5xx, 403, etc.)
      console.error('Failed to load chat:', err);
      const errorDetails = extractErrorMessage(err); // Use the structured error handler
      setError(errorDetails); // Set the structured error state
      setChat(null); // Ensure chat state is null on error
      setMessages([]); // Clear messages on error
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
    });
  };
  
  if (loading) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '50vh' }}>
        <Spin size="large" />
      </div>
    );
  }

  // Check for error state first
  if (error) {
    return (
      <div style={{ textAlign: 'center', marginTop: 50 }}>
        {error.type === 'notFound' ? (
          <>
            <Title level={3}>Chat Not Found</Title>
            <Paragraph>{error.message || "The requested chat could not be found or access is denied."}</Paragraph>
          </>
        ) : error.type === 'forbidden' ? (
           <>
            <Title level={3}>Access Denied</Title>
            <Paragraph>{error.message || "You do not have permission to view this chat."}</Paragraph>
          </>
        ) : (
          <>
            <Title level={3}>Error Loading Chat</Title>
            <Paragraph>{error.message || "An unexpected error occurred while loading the chat."}</Paragraph>
          </>
        )}
        <Button type="primary" onClick={() => router.push('/chat')}>
          Return to Chat List
        </Button>
      </div>
    );
  }

  // If not loading and no error, check if chat data exists
  if (!chat) {
     // This case should ideally be covered by the error state now,
     // but keep as a fallback if error state wasn't set correctly.
     return (
        <div style={{ textAlign: 'center', marginTop: 50 }}>
          <Title level={3}>Chat Not Found</Title>
          <Paragraph>The requested chat could not be found or has been deleted.</Paragraph>
          <Button type="primary" onClick={() => router.push('/chat')}>
            Return to Chat List
          </Button>
        </div>
      );
  }

  // If not loading, no error, and chat exists, render the chat content
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

// Wrap the component with the HOC for authentication
export default withAuth(ChatPage);

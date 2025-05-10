import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useRouter } from 'next/router';
import { 
  Typography, 
  Input, 
  Button, 
  Card, 
  message, 
  Spin,
  Tooltip
} from 'antd';
import { 
  SendOutlined, 
  CopyOutlined
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
  const [isSendingInitial, setIsSendingInitial] = useState<boolean>(false); // New state for initial message sending
  const [newMessage, setNewMessage] = useState('');
  const [error, setError] = useState<{ type: string, message: string, status?: number } | null>(null); // Updated error state type
  
  // Refs
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textAreaRef = useRef<any>(null);
  const initialMessageSentRef = useRef<boolean>(false); // Add this line

  // Define loadChat with useCallback before it's used in useEffect
  const loadChat = useCallback(async (chatId: number) => {
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
  }, []); // Empty dependency array as loadChat doesn't depend on component state that changes frequently here.
  
  // Load chat data when id changes or router is ready
  useEffect(() => {
    if (router.isReady && id) {
      const chatIdNum = parseInt(id as string); // Ensure numeric ID
      // Removed duplicate declaration of chatIdNum
      if (!isNaN(chatIdNum)) { // Ensure id is a valid number
        loadChat(chatIdNum);
      } else {
        setError({ type: 'notFound', message: `Invalid chat ID: ${id}`, status: 400 });
        setLoading(false);
      }
    }
  }, [id, router.isReady, loadChat]); // Added loadChat to dependency array
  
  // Scroll to bottom when messages change or initial message sending finishes
  useEffect(() => {
    scrollToBottom();
  }, [messages, isSendingInitial]); // Depend on messages and isSendingInitial
  
  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };
  
  // Effect to handle initial message from query parameter
  useEffect(() => {
    // Ensure router is ready, an id is present, an initialMessage exists in query, AND it hasn't been sent yet
    if (router.isReady && id && router.query.initialMessage && !initialMessageSentRef.current) {
      const initialMessageContent = router.query.initialMessage as string; // router.query.initialMessage is guaranteed by the check above
      const currentChatId = id as string; // id is guaranteed by the check above
      const chatIdNum = parseInt(currentChatId);

      if (!isNaN(chatIdNum)) {
        console.log(`Processing initial message for chat ${currentChatId}: "${initialMessageContent}" (Ref Guard)`);
        initialMessageSentRef.current = true; // Set the ref flag immediately and synchronously
        setIsSendingInitial(true); // Start initial sending loading state

        const sendInitialMessageAsync = async () => {
          try {
            // Create the user message in the backend
            await chatService.createMessage({
              chat_id: chatIdNum,
              sender: 'user',
              content: initialMessageContent
            });
            console.log("Initial user message created.");

            // Send the question to the LLM
            await chatService.askQuestion({
              chat_id: chatIdNum,
              content: initialMessageContent,
            });
            console.log("Initial question sent to LLM.");

            // Refresh the chat messages to include the user's message and AI's response
            await loadChat(chatIdNum);
            console.log("Chat messages refreshed after initial message.");

          } catch (error) {
            console.error('Failed to send initial message or get response:', error);
            message.error(extractErrorMessage(error).message || 'Failed to send initial message.');
          } finally {
            // Remove the initialMessage query parameter only if it was the one we just processed
            // This check is important if the effect re-runs after router.replace already cleared it
            if (router.query.initialMessage === initialMessageContent) {
                router.replace(`/chat/${currentChatId}`, undefined, { shallow: true });
            }
            setIsSendingInitial(false); // End initial sending loading state
            console.log("Initial message processing finished.");
          }
        };
        sendInitialMessageAsync();
      } else {
        setError({ type: 'notFound', message: `Invalid chat ID for initial message: ${currentChatId}`, status: 400 });
        setIsSendingInitial(false);
        initialMessageSentRef.current = true; // Mark as processed to avoid retries
        if (router.query.initialMessage) { // Clear query if it was there
            router.replace(`/chat/${currentChatId}`, undefined, { shallow: true });
        }
      }
    }
  }, [
    router.isReady,
    router.query.initialMessage, // Depend explicitly on the query parameter
    id,                          // Depend on the chat ID from the path
    loadChat                     // loadChat is memoized
    // Note: Do not add initialMessageSentRef.current to the dependency array.
  ]);


  const handleSendMessage = async () => {
    // Disable sending if initial message is still being processed
    if (!newMessage.trim() || !chat || sending || isSendingInitial) return;

    const userMessageData: MessageCreate = {
      chat_id: chat.id,
      sender: 'user',
      content: newMessage
    };

    try {
      setSending(true);

      // Clear input field immediately
      const messageContent = newMessage;
      setNewMessage('');

      // Focus back on the textarea
      if (textAreaRef.current) {
        textAreaRef.current.focus();
      }

      // Create user message in backend
      await chatService.createMessage(userMessageData);

      // Now ask the question and get answer
      await chatService.askQuestion({
        chat_id: chat.id,
        content: messageContent, // Use the stored content
      });

      // Refresh messages from server to ensure consistency and include AI response
      await loadChat(chat.id);

    } catch (error) {
      console.error('Failed to send message:', error);
      message.error(extractErrorMessage(error).message || 'Failed to send message');
      // If sending fails, you might want to restore the message content
      // setNewMessage(messageContent); // Optional: restore message on error
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
            marginBottom: 12,
          }}
        >
          <Card
            className={isUser ? 'user-message-card' : 'assistant-message-card'}
            style={{ maxWidth: '80%' }}
            bodyStyle={{ padding: '10px 14px' }}
          >
            <div style={{ flex: 1 }}>
              <Paragraph style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word', marginBottom: 0 }}>
                {msg.content}
              </Paragraph>
              <div style={{ display: 'flex', justifyContent: 'flex-end', alignItems: 'center' }}>
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
    <div style={{ height: 'calc(100vh - 110px)', display: 'flex', flexDirection: 'column' }}>
      <div style={{ flex: 1, overflowY: 'auto', padding: '16px 4px' }}>
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
      
      <div style={{ padding: '16px 0', borderTop: '1px solid var(--border-color)' }}>
        <div style={{ display: 'flex', alignItems: 'flex-end' }}>
          <TextArea
            ref={textAreaRef}
            value={newMessage}
            onChange={(e) => setNewMessage(e.target.value)}
            placeholder="Type your message here..."
            autoSize={{ minRows: 2, maxRows: 6 }}
            disabled={sending || isSendingInitial} // Disable if sending or processing initial message
            onPressEnter={(e) => {
              if (!e.shiftKey) {
                e.preventDefault();
                handleSendMessage();
              }
            }}
            style={{ flex: 1, marginRight: 8, borderRadius: '4px' }}
          />
          <Button
            type="primary"
            icon={<SendOutlined />}
            onClick={handleSendMessage}
            loading={sending || isSendingInitial} // Show loading if sending or processing initial message
            disabled={!newMessage.trim() || sending || isSendingInitial} // Disable if empty, sending, or processing initial message
            style={{ height: 'auto', minHeight: '32px', borderRadius: '4px' }}
          />
        </div>
        <Text type="secondary" style={{ fontSize: '12px', marginTop: 4, display: 'block', textAlign: 'center' }}>
          Press Enter to send, Shift+Enter for new line
        </Text>
      </div>
    </div>
  );
};

// Wrap the component with the HOC for authentication
export default withAuth(ChatPage);
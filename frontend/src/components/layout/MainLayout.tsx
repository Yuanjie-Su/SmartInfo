import React, { useState, useEffect } from 'react';
import { Layout, Menu, Button, Input, Space, Typography, Divider, Spin } from 'antd'; // Added Spin
import {
  FileTextOutlined,
  MessageOutlined,
  SettingOutlined,
  PlusOutlined,
  SearchOutlined,
  LoginOutlined,
  LogoutOutlined,
  UserOutlined
} from '@ant-design/icons';
import { useRouter } from 'next/router';
import Link from 'next/link';
import { useAuth } from '@/context/AuthContext'; // Import useAuth hook
import { Chat } from '@/utils/types';
import * as chatService from '@/services/chatService';

const { Header, Sider, Content } = Layout;
const { Text } = Typography;
const { Search } = Input;

// Helper to format chat date for grouping
const formatChatDate = (timestampInput: number | string | undefined | null): string => {
  if (!timestampInput) {
    return 'Others'; // Or handle as appropriate
  }

  let chatTimestamp: number;
  if (typeof timestampInput === 'string') {
    // Attempt to parse if it's a string (e.g., ISO string or timestamp string)
    const parsedDate = new Date(timestampInput);
    if (isNaN(parsedDate.getTime())) {
      // If parsing fails, try parsing as a number (Unix timestamp string)
      const parsedNum = parseInt(timestampInput, 10);
      if (!isNaN(parsedNum)) {
        chatTimestamp = parsedNum * 1000; // Assume seconds if it's a number string
      } else {
        return 'Others'; // Invalid date string
      }
    } else {
      chatTimestamp = parsedDate.getTime(); // Use milliseconds from Date object
    }
  } else if (typeof timestampInput === 'number') {
    // Assume it's a Unix timestamp in seconds, convert to milliseconds
    chatTimestamp = timestampInput * 1000;
  } else {
    return 'Others'; // Should not happen based on type check, but safe fallback
  }

  const now = new Date();
  const chatDate = new Date(chatTimestamp);

  // Check if chatDate is valid after all parsing attempts
  if (isNaN(chatDate.getTime())) {
      return 'Others';
  }

  // Same day?
  if (now.toDateString() === chatDate.toDateString()) {
    return 'Today';
  }
  
  // Yesterday?
  const yesterday = new Date(now);
  yesterday.setDate(now.getDate() - 1);
  if (yesterday.toDateString() === chatDate.toDateString()) {
    return 'Yesterday';
  }
  
  // Everything else
  return 'Others';
};

// Group chats by date category
const groupChatsByDate = (chats: Chat[]) => {
  const groups: Record<string, Chat[]> = {
    'Today': [],
    'Yesterday': [],
    'Others': []
  };
  
  chats.forEach(chat => {
    const group = formatChatDate(chat.created_at);
    groups[group].push(chat);
  });
  
  return groups;
};

interface MainLayoutProps {
  children: React.ReactNode;
}

const MainLayout: React.FC<MainLayoutProps> = ({ children }) => {
  const router = useRouter();
  const [collapsed, setCollapsed] = useState(false);
  const [searchText, setSearchText] = useState('');
  const [chats, setChats] = useState<Chat[]>([]);
  const [filteredChats, setFilteredChats] = useState<Chat[]>([]);
  const [selectedKey, setSelectedKey] = useState('news');
  const { isAuthenticated, user, logout, loading: authLoading } = useAuth(); // Get auth state and functions

  // Load chat history on component mount
  useEffect(() => {
    const loadChats = async () => {
      // Only attempt to load chats if authenticated
      if (isAuthenticated) { // <-- Add this check
        try {
          const result = await chatService.getChats();
          setChats(result);
          setFilteredChats(result);
        } catch (error) {
          console.error('Failed to load chats:', error);
          // Handle error appropriately, maybe clear chats
          setChats([]);
          setFilteredChats([]);
        }
      } else {
         // Clear chat list if not authenticated
         setChats([]);
         setFilteredChats([]);
      }
    };
    
    // Only run the effect when the initial auth check is complete
    if (!authLoading) { // <-- Add this check
      loadChats();
    }
  }, [isAuthenticated, authLoading]); // Add dependencies
  
  // Filter chats when search text changes
  useEffect(() => {
    if (!searchText.trim()) {
      setFilteredChats(chats);
      return;
    }
    
    const filtered = chats.filter(chat => 
      chat.title.toLowerCase().includes(searchText.toLowerCase())
    );
    setFilteredChats(filtered);
  }, [searchText, chats]);
  
  // Update selected key based on route
  useEffect(() => {
    const path = router.pathname;
    if (path === '/') {
      setSelectedKey('news');
    } else if (path === '/settings') {
      setSelectedKey('settings');
    } else if (path.startsWith('/chat')) {
      setSelectedKey(`chat-${router.query.id}`);
    }
  }, [router.pathname, router.query.id]);
  
  // Create a new chat
  const handleNewChat = async () => {
    try {
      const newChat = await chatService.createChat({ title: 'New Chat' });
      router.push(`/chat/${newChat.id}`);
      // Refresh chat list
      const updatedChats = await chatService.getChats();
      setChats(updatedChats);
      setFilteredChats(updatedChats);
    } catch (error) {
      console.error('Failed to create new chat:', error);
    }
  };
  
  // Grouped chats for display
  const groupedChats = groupChatsByDate(filteredChats);
  
  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Sider
        width={250}
        collapsible
        collapsed={collapsed}
        onCollapse={setCollapsed}
        style={{ 
          overflowY: 'auto',
          height: '100vh',
          position: 'fixed',
          left: 0,
          top: 0,
          bottom: 0
        }}
      >
        <div style={{ padding: '16px' }}>
          <Menu
            mode="inline"
            selectedKeys={[selectedKey]}
            style={{ borderRight: 0 }}
            items={[
              {
                key: 'news',
                icon: <FileTextOutlined />,
                label: <Link href="/">News</Link>,
              }
            ]}
          />
        </div>
        
        <Divider style={{ margin: '0 0 16px 0' }} />
        
        {/* Chat Section with Search and New Button */}
        <div style={{ padding: '0 16px 16px' }}>
          <Space style={{ marginBottom: '12px', width: '100%' }}>
            <Button 
              type="primary" 
              icon={<PlusOutlined />} 
              onClick={handleNewChat}
            />
            <Input 
              placeholder="Search chats" 
              prefix={<SearchOutlined />} 
              onChange={e => setSearchText(e.target.value)}
              style={{ flex: 1 }}
            />
          </Space>
          
          {/* Chat Groups */}
          {!collapsed && (
            <div>
              {Object.entries(groupedChats).map(([groupName, groupChats]) => 
                groupChats.length > 0 && (
                  <div key={groupName} style={{ marginBottom: '16px' }}>
                    <Text type="secondary" style={{ display: 'block', marginBottom: '8px' }}>
                      {groupName}
                    </Text>
                    <Menu
                      mode="inline"
                      selectedKeys={[selectedKey]}
                      style={{ borderRight: 0 }}
                      items={groupChats.map(chat => ({
                        key: `chat-${chat.id}`,
                        icon: <MessageOutlined />,
                        label: (
                          <Link href={`/chat/${chat.id}`}>
                            <div style={{ 
                              overflow: 'hidden', 
                              textOverflow: 'ellipsis', 
                              whiteSpace: 'nowrap' 
                            }}>
                              {chat.title}
                            </div>
                          </Link>
                        )
                      }))}
                    />
                  </div>
                )
              )}
            </div>
          )}
        </div>

        {/* User Status & Settings at the bottom */}
        <div style={{ position: 'absolute', bottom: 0, width: '100%', padding: '16px' }}>
          {/* User Status Section */}
          {!collapsed && ( // Only show details when not collapsed
            <div style={{ marginBottom: '16px', padding: '8px 0', borderTop: '1px solid rgba(255, 255, 255, 0.1)', borderBottom: '1px solid rgba(255, 255, 255, 0.1)' }}>
              {authLoading ? (
                <div style={{ textAlign: 'center' }}>
                  <Spin size="small" />
                </div>
              ) : isAuthenticated && user ? (
                <Space direction="vertical" style={{ width: '100%', padding: '0 8px' }}>
                  <Space>
                    <UserOutlined style={{ color: 'rgba(255, 255, 255, 0.65)' }} />
                    <Text style={{ color: 'rgba(255, 255, 255, 0.85)' }} ellipsis>
                      {user.username}
                    </Text>
                  </Space>
                  <Button
                    type="text"
                    icon={<LogoutOutlined />}
                    onClick={logout}
                    style={{ color: 'rgba(255, 255, 255, 0.65)', width: '100%', textAlign: 'left', paddingLeft: '8px' }}
                  >
                    Logout
                  </Button>
                </Space>
              ) : (
                 <Link href="/login" passHref>
                   <Button
                     type="text"
                     icon={<LoginOutlined />}
                     style={{ color: 'rgba(255, 255, 255, 0.65)', width: '100%', textAlign: 'left', paddingLeft: '8px' }}
                   >
                     Login
                   </Button>
                 </Link>
              )}
            </div>
          )}

          {/* Settings Menu */}
          <Menu
            mode="inline"
            selectedKeys={[selectedKey]}
            style={{ borderRight: 0 }}
            items={[
              {
                key: 'settings',
                icon: <SettingOutlined />,
                label: <Link href="/settings">Settings</Link>,
              }
            ]}
          />
          <div style={{ textAlign: 'center', marginTop: '8px' }}>
            <Text type="secondary">v1.0.0</Text>
          </div>
        </div>
      </Sider>
      
      <Layout style={{ marginLeft: collapsed ? 80 : 250, transition: 'margin-left 0.2s' }}>
        <Content style={{ margin: '24px 16px', padding: 24, minHeight: 280 }}>
          {children}
        </Content>
      </Layout>
    </Layout>
  );
};

export default MainLayout;

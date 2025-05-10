import React, { useState, useEffect } from 'react';
import { Layout, Menu, Button, Input, Space, Typography, Divider, Spin, Avatar, Tooltip } from 'antd';
import {
  ReadOutlined,
  MessageOutlined,
  SettingOutlined,
  PlusOutlined,
  SearchOutlined,
  LogoutOutlined,
  AppstoreOutlined
} from '@ant-design/icons';
import { useRouter } from 'next/router';
import Link from 'next/link';
import { useAuth } from '@/context/AuthContext';
import { Chat } from '@/utils/types';
import * as chatService from '@/services/chatService';
import styles from './MainLayout.module.css';

const { Sider, Content } = Layout;
const { Text, Title } = Typography;

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
  const { isAuthenticated, user, logout, loading: authLoading } = useAuth();

  useEffect(() => {
    const path = router.pathname;
    if (path === '/' || path.startsWith('/news') || path.startsWith('/analyze')) {
      setSelectedKey('news');
    } else if (path === '/settings') {
      setSelectedKey('settings');
    } else if (path.startsWith('/chat/')) {
      const chatId = router.query.id;
      setSelectedKey(chatId ? `chat-${chatId}` : 'chat-list');
    } else if (path === '/chat') {
        setSelectedKey('chat-list'); // General chat page
    }
  }, [router.pathname, router.query.id]);

  // Load chat history on component mount
  useEffect(() => {
    const loadChats = async () => {
      // Only attempt to load chats if authenticated
      if (isAuthenticated) { 
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
    if (!authLoading) { 
      loadChats();
    }
  }, [isAuthenticated, authLoading]); 
  
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
  
  const mainMenuItems = [
    {
      key: 'news',
      icon: <ReadOutlined />,
      label: <Link href="/">News Feed</Link>,
    },
  ];

  const bottomMenuItems = [
    {
      key: 'settings',
      icon: <SettingOutlined />,
      label: <Link href="/settings">Settings</Link>,
    }
  ];

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Sider
        width={260}
        collapsible
        collapsed={collapsed}
        onCollapse={setCollapsed}
        theme="light"
        className={styles.appSider}
        style={{
          overflow: 'auto',
          height: '100vh',
          position: 'fixed',
          left: 0,
          top: 0,
          bottom: 0,
          borderRight: `1px solid var(--border-color)`,
          paddingTop: '16px',
        }}
      >
        <div style={{ padding: `0 ${collapsed ? '0' : '24px'} 16px ${collapsed ? '0' : '24px'}`, textAlign: collapsed ? 'center' : 'left', height: '32px', marginBottom: '8px' }}>
          {collapsed ? (
            <Avatar style={{ backgroundColor: 'var(--accent-color)' }} size="default">S</Avatar>
          ) : (
            <Title level={4} style={{ margin: 0, color: 'var(--accent-color)', fontWeight: 600 }}>SmartInfo</Title>
          )}
        </div>

        <Menu
          mode="inline"
          selectedKeys={[selectedKey]}
          items={mainMenuItems}
          className={styles.siderMainMenu}
        />

        <Divider style={{ margin: '16px 24px' }} />

        <div style={{ padding: `0 ${collapsed ? '8px' : '16px'}` }}>
          {!collapsed && (
            <Space.Compact style={{ width: '100%', marginBottom: '16px' }}>
              <Input
                prefix={<SearchOutlined style={{ color: 'var(--text-secondary)'}} />}
                placeholder="Search chats"
                value={searchText}
                onChange={e => setSearchText(e.target.value)}
                allowClear
              />
              <Tooltip title="New Chat">
                <Button
                  icon={<PlusOutlined />}
                  onClick={handleNewChat}
                  aria-label="New Chat"
                />
              </Tooltip>
            </Space.Compact>
          )}

          {!collapsed && (authLoading ? (
            <div style={{padding: '20px', textAlign: 'center'}}><Spin size="small" /></div>
          ) : (
            Object.entries(groupedChats).map(([groupName, groupChatsList]) =>
              groupChatsList.length > 0 && (
                <div key={groupName} style={{ marginBottom: '12px' }}>
                  <Text className={styles.chatGroupTitle}>
                    {groupName}
                  </Text>
                  <Menu
                    mode="inline"
                    selectedKeys={[selectedKey]}
                    items={groupChatsList.map(chat => ({
                      key: `chat-${chat.id}`,
                      icon: <MessageOutlined />,
                      label: (
                        <Link href={`/chat/${chat.id}`}>
                          <Text ellipsis={{ tooltip: chat.title }}>{chat.title}</Text>
                        </Link>
                      )
                    }))}
                    className={styles.siderChatMenu}
                  />
                </div>
              )
            )
          ))}
        </div>

        <div className={styles.siderBottomSection}>
          <Menu
            mode="inline"
            selectedKeys={[selectedKey]}
            items={bottomMenuItems}
            className={styles.siderBottomMenu}
          />
          {!authLoading && isAuthenticated && (
            <Tooltip title={collapsed ? "Logout" : ""}>
              <Button
                type="text"
                icon={<LogoutOutlined />}
                onClick={logout}
                className={styles.logoutButton}
                aria-label="Logout"
              >
                {!collapsed && 'Logout'}
              </Button>
            </Tooltip>
          )}
          {!collapsed && (
            <div style={{ textAlign: 'center', marginTop: '8px', paddingBottom: '8px' }}>
              <Text type="secondary" style={{ fontSize: '11px' }}>v1.0.0</Text>
            </div>
          )}
        </div>
      </Sider>

      <Layout style={{ marginLeft: collapsed ? 80 : 260, transition: 'margin-left 0.2s' }}>
        <Content style={{ padding: 24, margin: 0, minHeight: 'calc(100vh - 48px)' }}>
          {children}
        </Content>
      </Layout>
    </Layout>
  );
};

export default MainLayout;

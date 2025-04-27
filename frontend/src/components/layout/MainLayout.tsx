import React, { useState, useEffect } from 'react';
import { Layout, Menu, Button, Input, Space, Typography, Divider } from 'antd';
import { 
  FileTextOutlined, 
  MessageOutlined, 
  SettingOutlined,
  PlusOutlined,
  SearchOutlined
} from '@ant-design/icons';
import { useRouter } from 'next/router';
import Link from 'next/link';
import { Chat } from '@/utils/types';
import * as chatService from '@/services/chatService';

const { Header, Sider, Content } = Layout;
const { Text } = Typography;
const { Search } = Input;

// Helper to format chat date for grouping
const formatChatDate = (dateString: string) => {
  const now = new Date();
  const chatDate = new Date(dateString);
  
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
    const group = formatChatDate(chat.created_at || new Date().toISOString());
    if (groups[group]) {
      groups[group].push(chat);
    } else {
      groups['Others'].push(chat);
    }
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
  
  // Load chat history on component mount
  useEffect(() => {
    const loadChats = async () => {
      try {
        const result = await chatService.getChats();
        setChats(result);
        setFilteredChats(result);
      } catch (error) {
        console.error('Failed to load chats:', error);
      }
    };
    
    loadChats();
  }, []);
  
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
        
        {/* Settings at the bottom */}
        <div style={{ position: 'absolute', bottom: 0, width: '100%', padding: '16px' }}>
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
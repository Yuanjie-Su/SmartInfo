import React, { useState, useEffect, useRef, useCallback } from 'react';
import { Layout, Menu, Button, Input, Space, Typography, Divider, Spin, Avatar, Tooltip, Dropdown, Modal, Form as AntForm, message } from 'antd';
import {
  ReadOutlined,
  MessageOutlined,
  SettingOutlined,
  PlusOutlined,
  SearchOutlined,
  LogoutOutlined,
  AppstoreOutlined,
  EllipsisOutlined // Added EllipsisOutlined
} from '@ant-design/icons';
import { useRouter } from 'next/router';
import Link from 'next/link';
import { useAuth } from '@/context/AuthContext';
import { Chat } from '@/utils/types';
import * as chatService from '@/services/chatService';
import { extractErrorMessage } from '@/utils/apiErrorHandler'; // For error handling
import axios from 'axios'; // For checking API error type
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
  const [hoveredChatId, setHoveredChatId] = useState<number | null>(null);
  const [isRenameModalVisible, setIsRenameModalVisible] = useState(false);
  const [renamingChatDetails, setRenamingChatDetails] = useState<{ id: number; currentTitle: string } | null>(null);
  const [renameForm] = AntForm.useForm(); // Form instance for rename modal
  const router = useRouter();
  const [collapsed, setCollapsed] = useState(false);
  const [searchText, setSearchText] = useState('');
  const [chats, setChats] = useState<Chat[]>([]);
  const [filteredChats, setFilteredChats] = useState<Chat[]>([]);
  const [selectedKey, setSelectedKey] = useState('news');
  const { isAuthenticated, user, logout, loading: authLoading, setRefreshChatListCallback } = useAuth(); // Get setRefreshChatListCallback

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

   // Define a single, memoized loadChats function
  const loadChats = useCallback(async () => {
    if (isAuthenticated) {
      try {
        const result = await chatService.getChats();
        setChats(result);
        setFilteredChats(result); // Also update filteredChats initially
      } catch (error) {
        console.error('Failed to load chats:', error);
        setChats([]);
        setFilteredChats([]);
      }
    } else {
      setChats([]);
      setFilteredChats([]);
    }
  }, [isAuthenticated]); // Correctly memoized, depends on isAuthenticated

  // Load chat history on component mount and set up refresh callback
  useEffect(() => {
    // Only run the effect when the initial auth check is complete
    if (!authLoading) {  
      loadChats(); // Call the memoized function for initial load
    }

    // Set the callback for refreshing chat list
    if (setRefreshChatListCallback) {
      setRefreshChatListCallback(loadChats); // Pass the memoized function
    }

    // Cleanup callback on unmount
    return () => {
      if (setRefreshChatListCallback) {
        setRefreshChatListCallback(null);
      }
    };
  }, [authLoading, loadChats, setRefreshChatListCallback]);
  
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
  
  // Handle new chat button click
  const handleNewChat = () => {
    // Check if already on the default chat page
    if (router.pathname === '/chat') {
      console.log('Already on default chat page.');
      // Do nothing, user can just start typing
    } else {
      console.log('Navigating to default chat page /chat');
      // Navigate to the default chat page
      router.push('/chat');
      // The useEffect that watches router.pathname will handle updating selectedKey
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

  const showRenameModal = (chatId: number, currentTitle: string) => {
    setRenamingChatDetails({ id: chatId, currentTitle });
    renameForm.setFieldsValue({ newTitle: currentTitle });
    setIsRenameModalVisible(true);
  };

  const handleRenameOk = async () => {
    if (!renamingChatDetails) return;
    try {
      const values = await renameForm.validateFields();
      await chatService.updateChat(renamingChatDetails.id, { title: values.newTitle });
      message.success('Chat renamed successfully');
      await loadChats();
      setIsRenameModalVisible(false);
      renameForm.resetFields();
      // If the renamed chat is the currently selected one, update the page title or other UI elements if necessary
      if (selectedKey === `chat-${renamingChatDetails.id}`) {
        // Potentially update document.title or a local state for the page title if MainLayout controls it
      }
    } catch (errorInfo) {
      if (axios.isAxiosError(errorInfo)) {
        message.error(extractErrorMessage(errorInfo).message || 'Failed to rename chat.');
      } else {
        console.log('Rename form validation failed:', errorInfo);
      }
    }
  };

  const handleRenameCancel = () => {
    setIsRenameModalVisible(false);
    renameForm.resetFields();
  };

  const handleDeleteChat = (chatId: number) => {
    Modal.confirm({
      title: 'Delete Chat',
      content: 'Are you sure you want to delete this chat session and all its messages?',
      okText: 'Delete',
      okType: 'danger',
      cancelText: 'Cancel',
      onOk: async () => {
        try {
          await chatService.deleteChat(chatId);
          message.success('Chat deleted successfully');
          await loadChats();
          if (router.query.id && parseInt(router.query.id as string) === chatId) {
            router.push('/chat');
          } else if (selectedKey === `chat-${chatId}`) {
            // If the deleted chat was selected in the sidebar, navigate to the general chat page or select another chat
            const newChats = chats.filter(c => c.id !== chatId);
            if (newChats.length > 0) {
              // router.push(`/chat/${newChats[0].id}`); // Optionally select the first available chat
            } else {
              router.push('/chat'); // Or go to the generic chat page if no chats are left
            }
          }
        } catch (error) {
          message.error(extractErrorMessage(error).message || 'Failed to delete chat');
        }
      },
    });
  };

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
                    // onClick={(e) => router.push(`/chat/${e.key.replace('chat-', '')}`)} // Main navigation can be handled by Menu's onClick or Link's onClick
                    items={groupChatsList.map(chat => {
                      const menuKey = `chat-${chat.id}`;
                      return {
                        key: menuKey,
                        label: (
                          <div
                            onMouseEnter={() => setHoveredChatId(chat.id)}
                            onMouseLeave={() => setHoveredChatId(null)}
                            style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', width: '100%' }}
                          >
                            <Link href={`/chat/${chat.id}`} passHref legacyBehavior>
                              <a style={{ flexGrow: 1, overflow: 'hidden', textDecoration: 'none', color: 'inherit' }}
                                 onClick={(e) => {
                                   // Prevent Link navigation if the click is on the actions button area
                                   if ((e.target as HTMLElement).closest('.chat-item-actions-trigger')) {
                                     e.preventDefault();
                                   }
                                 }}
                              >
                                <Text ellipsis={{ tooltip: chat.title }} style={{ display: 'block', lineHeight: '22px' }}>
                                  {chat.title}
                                </Text>
                              </a>
                            </Link>
                            {hoveredChatId === chat.id && !collapsed && (
                              <Dropdown
                                menu={{
                                  items: [
                                    {
                                      key: 'rename',
                                      label: 'Rename',
                                      onClick: (info) => {
                                        info.domEvent.stopPropagation();
                                        info.domEvent.preventDefault();
                                        showRenameModal(chat.id, chat.title);
                                      }
                                    },
                                    {
                                      key: 'delete',
                                      label: 'Delete',
                                      danger: true,
                                      onClick: (info) => {
                                        info.domEvent.stopPropagation();
                                        info.domEvent.preventDefault();
                                        handleDeleteChat(chat.id);
                                      }
                                    },
                                  ]
                                }}
                                trigger={['click']} // Changed to click trigger
                                placement="bottomRight"
                              >
                                <Button
                                  className="chat-item-actions-trigger" // Class to identify the button
                                  type="text"
                                  icon={<EllipsisOutlined />}
                                  size="small"
                                  style={{ flexShrink: 0, marginLeft: '8px' }}
                                  onClick={(e) => { // This button's click will open the Dropdown
                                    e.stopPropagation(); // Prevent Menu.Item's own onClick (if any for navigation)
                                    e.preventDefault(); // Prevent any default browser action
                                  }}
                                />
                              </Dropdown>
                            )}
                          </div>
                        ),
                      };
                    })}
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

      <Modal
        title="Rename Chat"
        open={isRenameModalVisible}
        onOk={handleRenameOk}
        onCancel={handleRenameCancel}
        // confirmLoading={/* Add loading state for rename operation if needed */}
      >
        <AntForm form={renameForm} layout="vertical" name="rename_chat_form">
          <AntForm.Item
            name="newTitle"
            label="New Chat Title"
            rules={[{ required: true, message: 'Please enter the new title.' }]}
          >
            <Input />
          </AntForm.Item>
        </AntForm>
      </Modal>
    </Layout>
  );
};

export default MainLayout;

import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useAuth } from '@/context/AuthContext'; // 导入认证上下文
import {
  Typography,
  Select,
  Input,
  Spin,
  Empty,
  List,
  Card,
  Row,
  Col,
  Pagination,
  Space,
  Button,
  Alert,
  Tag,
  Divider,
  Modal,
  Form,
  Checkbox,
  Drawer,
  Progress,
  message,
  Tooltip
} from 'antd';
import {
  SearchOutlined,
  CalendarOutlined,
  TagOutlined,
  GlobalOutlined,
  ExperimentOutlined,
  DownloadOutlined,
  BarsOutlined,
  LinkOutlined
} from '@ant-design/icons';
import { NewsItem, NewsCategory, NewsSource, NewsFilterParams, FetchTaskItem } from '@/utils/types';
import * as newsService from '@/services/newsService';
import { handleApiError } from '@/utils/apiErrorHandler';
import Link from 'next/link';
import debounce from 'lodash/debounce';
import type { CheckboxChangeEvent } from 'antd/es/checkbox';
import AnalysisModal from '@/components/analysis/AnalysisModal';
import withAuth from '@/components/auth/withAuth'; // Import the HOC

const { Title, Text, Paragraph } = Typography;
const { Option } = Select;

const NewsPage: React.FC = () => {
  // 添加认证上下文
  const { token } = useAuth();
  
  // State
  const [news, setNews] = useState<NewsItem[]>([]);
  const [categories, setCategories] = useState<NewsCategory[]>([]);
  const [sources, setSources] = useState<NewsSource[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [filters, setFilters] = useState<NewsFilterParams>({
    page: 1,
    page_size: 10,
    category_id: undefined,
    source_id: undefined,
    search_term: '',
  });
  const [total, setTotal] = useState(0);

  // New fetch settings modal state
  const [isFetchModalVisible, setIsFetchModalVisible] = useState<boolean>(false);
  const [selectedFetchCategory, setSelectedFetchCategory] = useState<number | undefined>(undefined);
  const [filteredFetchSources, setFilteredFetchSources] = useState<NewsSource[]>([]);
  const [selectedSourceIds, setSelectedSourceIds] = useState<number[]>([]);
  const [selectAllSources, setSelectAllSources] = useState<boolean>(false);
  const [isIndeterminate, setIsIndeterminate] = useState<boolean>(false);

  // Task progress drawer state
  const [isTaskDrawerVisible, setIsTaskDrawerVisible] = useState<boolean>(false);
  const [tasksToMonitor, setTasksToMonitor] = useState<FetchTaskItem[]>([]);

  // Analysis modal state
  const [analysisModalVisible, setAnalysisModalVisible] = useState<boolean>(false);
  const [selectedNewsItemId, setSelectedNewsItemId] = useState<number | null>(null);

  // WebSocket state
  const [taskGroupId, setTaskGroupId] = useState<string | null>(null);
  const wsRef = useRef<WebSocket | null>(null);

  // Load news data
  const loadNews = useCallback(async (params: NewsFilterParams) => {
    try {
      setLoading(true);
      setError(null);
      const newsData = await newsService.getNewsItems(params);
      setNews(newsData);
      setTotal(100);
    } catch (error) {
      handleApiError(error, 'Failed to load news');
      setError('Cannot load news content, please try again later');
    } finally {
      setLoading(false);
    }
  }, []);

  // Debounced search handler
  const debouncedSearch = useCallback(
    debounce((value: string) => {
      setFilters(prev => ({...prev, search_term: value, page: 1}));
    }, 500),
    []
  );

  // Handle filter changes
  const handleFilterChange = (key: keyof NewsFilterParams, value: any) => {
    setFilters(prev => {
      const updated = {...prev, [key]: value};
      // Reset page number when filter conditions change
      if (key !== 'page') {
        updated.page = 1;
      }
      return updated;
    });
  };

  // Handle category changes
  const handleCategoryChange = async (value: number | undefined) => {
    try {
      // Update filters
      handleFilterChange('category_id', value);

      // If a category is selected, get sources for that category
      if (value !== undefined) {
        const sourcesData = await newsService.getSourcesByCategory(value);
        setSources(sourcesData);
      } else {
        // If "All" is selected, get all sources
        const sourcesData = await newsService.getSources();
        setSources(sourcesData);
      }

      // Reset source filter
      handleFilterChange('source_id', undefined);
    } catch (error) {
      handleApiError(error, 'Cannot update source list for category');
    }
  };

  // Function to establish WebSocket connection
  const connectWebSocket = useCallback((groupId: string) => {
    // Close existing connection if any
    if (wsRef.current) {
      console.log('Closing previous WebSocket connection.');
      wsRef.current.close();
    }

    // 验证是否有认证令牌
    if (!token) {
      console.error('No authentication token available. Cannot establish WebSocket connection.');
      message.error('无法建立WebSocket连接：未登录或会话已过期');
      return;
    }

    // Construct WebSocket URL with authentication token as a query parameter
    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    // Use API_URL base but replace http/https with ws/wss and remove potential trailing slash
    const apiUrlBase = (process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000').replace(/^http/, 'ws').replace(/\/$/, '');
    // 添加token作为查询参数
    const wsUrl = `${apiUrlBase}/api/tasks/ws/tasks/${groupId}?token=${encodeURIComponent(token)}`;
    console.log('Connecting to WebSocket with auth token:', wsUrl);

    try {
        const ws = new WebSocket(wsUrl);
        wsRef.current = ws; // Store the instance

        ws.onopen = () => {
          console.log(`WebSocket connected for task group: ${groupId}`);
          message.success(`Connected to real-time progress updates (Group: ${groupId.substring(0, 6)}...)`);
        };

        ws.onmessage = (event) => {
          try {
              const taskUpdate = JSON.parse(event.data);
              console.log('Received task update:', taskUpdate);
              
              // 只处理包含source_id的消息
              if (taskUpdate.source_id === undefined) {
                  console.log('Received message without source_id (ignoring for task list):', taskUpdate);
                  return;
              }
              
              // 更新特定source任务的状态
              setTasksToMonitor(prevTasks => {
                  const taskIndex = prevTasks.findIndex(t => t.sourceId === taskUpdate.source_id);
  
                  if (taskIndex === -1) {
                      console.warn(`Received update for source ID ${taskUpdate.source_id}, but task not found in monitor list.`);
                      return prevTasks;
                  }

                  const updatedTasks = [...prevTasks];
                  const taskToUpdate = { ...updatedTasks[taskIndex] };
  
                  // 根据接收到的消息更新字段
                  taskToUpdate.status = taskUpdate.status || taskUpdate.step || taskToUpdate.status;
                  taskToUpdate.progress = taskUpdate.progress !== undefined ? taskUpdate.progress : taskToUpdate.progress;
                  taskToUpdate.message = taskUpdate.message || taskToUpdate.message;
                  if (taskUpdate.items_saved !== undefined) {
                      taskToUpdate.items_saved = taskUpdate.items_saved;
                  }
  
                  updatedTasks[taskIndex] = taskToUpdate;
                  return updatedTasks;
              });
          } catch (e) {
              console.error('Failed to parse or process WebSocket message:', e);
          }
        };

        ws.onerror = (error) => {
          console.error('WebSocket error:', error);
          message.error('WebSocket connection error.');
          // Optionally attempt to reconnect or clear the connection ref
          wsRef.current = null;
          setTaskGroupId(null); // Reset task group ID so user can try again
        };

        ws.onclose = (event) => {
          console.log(`WebSocket closed for task group: ${groupId}. Code: ${event.code}, Reason: ${event.reason}`);
          // Clear the ref when closed, unless it was intentionally closed to open a new one
          if (wsRef.current === ws) {
             wsRef.current = null;
             // Optionally reset taskGroupId if connection is lost unexpectedly
             // setTaskGroupId(null);
          }
        };
    } catch (err) {
        console.error("Failed to create WebSocket:", err);
        message.error("Failed to initialize WebSocket connection.");
    }

  }, [token]); // 添加token作为依赖，确保当token变化时函数被重新创建

  // Effect to connect WebSocket when taskGroupId changes
  useEffect(() => {
    if (taskGroupId) {
      connectWebSocket(taskGroupId);
    }

    // Cleanup function to close WebSocket when component unmounts or taskGroupId changes
    return () => {
      if (wsRef.current) {
        console.log('Closing WebSocket connection on cleanup.');
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, [taskGroupId, connectWebSocket]);

  // Load initial data
  useEffect(() => {
    const loadInitialData = async () => {
      try {
        setLoading(true);
        const [categoriesData, sourcesData] = await Promise.all([
          newsService.getCategories(),
          newsService.getSources()
        ]);

        setCategories(categoriesData);
        setSources(sourcesData);
        setFilteredFetchSources(sourcesData); // Initialize filtered sources for fetch modal
      } catch (error) {
        handleApiError(error, 'Failed to load initial data');
        setError('Cannot load categories and sources, please refresh the page and try again');
      } finally {
        setLoading(false);
      }
    };

    loadInitialData();
  }, []);

  // Load news when filters change
  useEffect(() => {
    loadNews(filters);
  }, [filters, loadNews]);

  // Format date display
  const formatDate = (dateString?: string) => {
    if (!dateString) return 'Unknown date';
    const date = new Date(dateString);
    return date.toLocaleDateString('en-US');
  };

  // Show fetch modal
  const showFetchModal = () => {
    // Reset internal modal state
    setSelectedFetchCategory(undefined); // Default to 'All Categories'
    setFilteredFetchSources(sources); // Show all sources initially
    setSelectedSourceIds([]);
    setSelectAllSources(false);
    setIsIndeterminate(false);
    // Open the modal
    setIsFetchModalVisible(true);
  };

  // Handle fetch category change in modal
  const handleFetchCategoryChange = (value: number | undefined) => {
    setSelectedFetchCategory(value);
    const newFilteredSources = value === undefined ? sources : sources.filter(s => s.category_id === value);
    setFilteredFetchSources(newFilteredSources);
    // Reset source selection and select-all state
    setSelectedSourceIds([]);
    setSelectAllSources(false);
    setIsIndeterminate(false);
  };

  // Handle source selection change in modal
  const handleSourceSelectionChange = (checkedValues: any[]) => {
    const numberValues = checkedValues as number[];
    setSelectedSourceIds(numberValues);
    const allVisibleSourceIds = filteredFetchSources.map(s => s.id);
    const allSelected = allVisibleSourceIds.length > 0 && numberValues.length === allVisibleSourceIds.length;
    const indeterminate = numberValues.length > 0 && numberValues.length < allVisibleSourceIds.length;
    setSelectAllSources(allSelected);
    setIsIndeterminate(indeterminate);
  };

  // Handle select all checkbox change in modal
  const handleSelectAllChange = (e: CheckboxChangeEvent) => {
    const isChecked = e.target.checked;
    const allVisibleSourceIds = filteredFetchSources.map(s => s.id);
    setSelectedSourceIds(isChecked ? allVisibleSourceIds : []);
    setSelectAllSources(isChecked);
    setIsIndeterminate(false);
  };

  // Handle fetch confirmation (OK button in modal)
  const handleFetchConfirm = async () => {
    if (selectedSourceIds.length === 0) {
      message.warning('Please select at least one news source.');
      return;
    }

    // Find the full source objects from the main 'sources' list
    const selectedSourcesDetails = sources.filter(s => selectedSourceIds.includes(s.id));

    // Create the new task items
    const newTasks: FetchTaskItem[] = selectedSourcesDetails.map(source => ({
      sourceId: source.id,
      sourceName: source.name,
      status: 'pending', // Initial status
      progress: 0,
    }));

    // Update UI state first for responsiveness
    setTasksToMonitor(prevTasks => [...prevTasks, ...newTasks]); // Append new tasks
    setIsFetchModalVisible(false);
    setIsTaskDrawerVisible(true); // Open the drawer immediately

    try {
      // Call the backend API to start batch fetch
      message.loading('Initiating fetch tasks...', 1);
      const response = await newsService.fetchNewsFromSourcesBatch(selectedSourceIds);

      // Store the task_group_id for WebSocket connection
      const taskGroupId = response.task_group_id;
      setTaskGroupId(taskGroupId); // This will trigger the useEffect to connect

      message.success(`Fetch tasks initiated successfully (Group ID: ${taskGroupId?.substring(0, 6)}...).`, 3);
    } catch (error) {
      // Handle API errors
      handleApiError(error, 'Failed to start news fetch tasks');
      // Remove the pending tasks from the monitor list if API call failed
      setTasksToMonitor(prevTasks => prevTasks.filter(task => !selectedSourceIds.includes(task.sourceId)));
    } finally {
      // Reset selections in the settings modal for next time
      setSelectedSourceIds([]);
      setSelectedFetchCategory(undefined);
      setFilteredFetchSources(sources);
      setSelectAllSources(false);
      setIsIndeterminate(false);
    }
  };

  // Helper function for status colors in task drawer
  const getStatusColor = (status: FetchTaskItem['status']) => {
    switch (status) {
      case 'pending': return 'default'; // Grey
      case 'fetching':
      case 'processing':
      case 'crawling':
      case 'analyzing':
      case 'saving':
      case 'initializing':
        return 'processing'; // Blue
      case 'complete': return 'success'; // Green
      case 'error': return 'error'; // Red
      default: return 'default';
    }
  };

  // Open analysis modal with the selected news item
  const openAnalysisModal = (newsItemId: number) => {
    setSelectedNewsItemId(newsItemId);
    setAnalysisModalVisible(true);
  };

  // Close analysis modal
  const closeAnalysisModal = () => {
    setAnalysisModalVisible(false);
    setSelectedNewsItemId(null);
  };

  return (
    <div>
      {/* Consolidated top controls in a single row */}
      <Row gutter={[16, 16]} style={{ marginBottom: 24 }} align="middle">
        <Col xs={24} sm={12} md={5} lg={5}>
          <Select
            placeholder="Select category"
            style={{ width: '100%' }}
            allowClear
            onChange={(value) => handleCategoryChange(value)}
            loading={loading && categories.length === 0}
          >
            {categories.map(category => (
              <Option key={category.id} value={category.id}>{category.name}</Option>
            ))}
          </Select>
        </Col>
        <Col xs={24} sm={12} md={5} lg={5}>
          <Select
            placeholder="Select source"
            style={{ width: '100%' }}
            allowClear
            onChange={(value) => handleFilterChange('source_id', value)}
            loading={loading && sources.length === 0}
          >
            {sources.map(source => (
              <Option key={source.id} value={source.id}>{source.name}</Option>
            ))}
          </Select>
        </Col>
        <Col xs={24} sm={24} md={8} lg={8}>
          <Input
            placeholder="Search news"
            prefix={<SearchOutlined />}
            onChange={(e) => debouncedSearch(e.target.value)}
            allowClear
          />
        </Col>
        <Col xs={12} sm={12} md={3} lg={3}>
          <Button type="primary" icon={<DownloadOutlined />} onClick={showFetchModal} style={{ width: '100%' }}>
            Get News
          </Button>
        </Col>
        <Col xs={12} sm={12} md={3} lg={3}>
          <Button icon={<BarsOutlined />} onClick={() => setIsTaskDrawerVisible(true)} style={{ width: '100%' }}>
            View Progress {tasksToMonitor.length > 0 ? `(${tasksToMonitor.filter(t => t.status !== 'complete' && t.status !== 'error').length})` : ''}
          </Button>
        </Col>
      </Row>

      {/* Error message */}
      {error && (
        <Alert
          message={error}
          type="error"
          showIcon
          style={{ marginBottom: 16 }}
        />
      )}

      {/* Loading state */}
      {loading ? (
        <div style={{ textAlign: 'center', padding: '50px 0' }}>
          <Spin size="large" tip="Loading..." />
        </div>
      ) : news.length === 0 ? (
        <Empty description="No news found" />
      ) : (
        <>
          {/* News list */}
          <List
            grid={{
              gutter: 16,
              xs: 1,
              sm: 1,
              md: 2,
              lg: 3,
              xl: 3,
              xxl: 4,
            }}
            dataSource={news}
            renderItem={(item) => (
              <List.Item>
                <Card hoverable style={{ borderRadius: '4px', boxShadow: 'none', border: '1px solid #f0f0f0' }}>
                  <Card.Meta
                    title={
                      <Tooltip title={item.title}>
                        <Text strong ellipsis style={{ fontSize: '16px', display: 'block', lineHeight: '1.4', maxHeight: '2.8em', overflow: 'hidden' }}>
                          {item.title}
                        </Text>
                      </Tooltip>
                    }
                    description={
                      <Space direction="vertical" size={8} style={{ width: '100%' }}>
                        {/* Date, Source, Category on one line */}
                        <Space size={16} wrap>
                          <Space size={4}>
                            <CalendarOutlined style={{ color: '#8c8c8c' }} />
                            <Text type="secondary" style={{ fontSize: '12px' }}>{formatDate(item.date)}</Text>
                          </Space>
                          <Space size={4}>
                            <GlobalOutlined style={{ color: '#8c8c8c' }} />
                            <Text type="secondary" style={{ fontSize: '12px' }}>{item.source_name}</Text>
                          </Space>
                          {/* --- Start modification for Category and Link --- */}
                          {/* Category */}
                          <Space size={4}>
                            <TagOutlined style={{ color: '#8c8c8c' }} />
                            <Text type="secondary" style={{ fontSize: '12px' }}>{item.category_name}</Text>
                          </Space>
                          {/* Original URL Link */}
                          {item.url && ( // Conditionally render link if URL exists
                            <Space size={4}>
                            <Tooltip title="查看原文">
                              <a href={item.url} target="_blank" rel="noopener noreferrer" style={{ color: 'inherit', display: 'inline-flex', alignItems: 'center' }}>
                              <LinkOutlined style={{ color: '#8c8c8c' }} />
                              </a>
                            </Tooltip>
                            </Space>
                          )}
                          {/* --- End modification --- */}
                        </Space>

                        {/* Summary with ellipsis */}
                        {item.summary && (
                          <Tooltip title={item.summary}>
                            <Paragraph ellipsis={{ rows: 3 }} style={{ marginBottom: '8px', color: '#595959' }}>
                              {item.summary}
                            </Paragraph>
                          </Tooltip>
                        )}

                        {/* Analysis button at bottom right - MODIFY HERE */}
                        <div style={{ textAlign: 'right' }}>
                          <Tooltip title="Analyze">
                            <Button
                              type="link"
                              icon={<ExperimentOutlined />}
                              onClick={() => openAnalysisModal(item.id)}
                            />
                          </Tooltip>
                        </div>
                      </Space>
                    }
                  />
                </Card>
              </List.Item>
            )}
          />

          {/* Pagination - centered with more info */}
          <div style={{ textAlign: 'center', marginTop: 24, display: 'flex', justifyContent: 'center' }}>
            <Pagination
              current={filters.page}
              pageSize={filters.page_size}
              total={total}
              onChange={(page) => handleFilterChange('page', page)}
              showSizeChanger
              onShowSizeChange={(_, size) => handleFilterChange('page_size', size)}
              showTotal={(total) => `Total ${total} items`}
            />
          </div>
        </>
      )}

      {/* Fetch Settings Modal */}
      <Modal
        title="News Fetch Settings"
        open={isFetchModalVisible}
        onOk={handleFetchConfirm}
        onCancel={() => setIsFetchModalVisible(false)}
        okText="Add to Task List"
        cancelText="Cancel"
        width={600}
      >
        <Spin spinning={loading && categories.length === 0}>
          <Form layout="vertical">
            {/* Category Filter */}
            <Form.Item label="Step 1: Filter News Categories (Optional)">
              <Select
                placeholder="Select category to filter sources below"
                allowClear
                value={selectedFetchCategory}
                onChange={handleFetchCategoryChange}
                style={{ width: '100%' }}
              >
                <Option value={undefined}>-- All Categories --</Option>
                {categories.map(cat => (
                  <Option key={cat.id} value={cat.id}>{cat.name}</Option>
                ))}
              </Select>
            </Form.Item>

            {/* Source Multi-Select */}
            <Form.Item label="Step 2: Select News Sources to Fetch">
              <Checkbox
                indeterminate={isIndeterminate}
                onChange={handleSelectAllChange}
                checked={selectAllSources}
                disabled={filteredFetchSources.length === 0}
                style={{ marginBottom: 8, display: 'block', borderBottom: '1px solid #f0f0f0', paddingBottom: '8px' }}
              >
                Select All/Deselect All ({filteredFetchSources.length} sources in current list)
              </Checkbox>
              <div style={{ maxHeight: '300px', overflowY: 'auto', border: '1px solid #f0f0f0', padding: '8px' }}>
                {filteredFetchSources.length > 0 ? (
                  <Checkbox.Group
                    style={{ width: '100%' }}
                    options={filteredFetchSources.map(s => ({ label: s.name, value: s.id }))}
                    value={selectedSourceIds}
                    onChange={handleSourceSelectionChange}
                  />
                ) : (
                  <Text type="secondary">Please select a category. No sources found for this category, or sources are not yet loaded.</Text>
                )}
              </div>
            </Form.Item>
          </Form>
        </Spin>
      </Modal>

      {/* Task Progress Drawer */}
      <Drawer
        title="Task Progress"
        placement="right"
        width={500}
        onClose={() => setIsTaskDrawerVisible(false)}
        open={isTaskDrawerVisible}
        mask={false}
        closable={true}
      >
        <List
          itemLayout="horizontal"
          dataSource={tasksToMonitor}
          locale={{ emptyText: 'No fetch tasks currently running or queued.' }}
          renderItem={(item: FetchTaskItem) => (
            <List.Item key={item.sourceId}>
              <List.Item.Meta
                title={item.sourceName}
                description={
                  <Space direction="vertical" size={2}>
                    <Tag color={getStatusColor(item.status)}>{item.status?.toUpperCase()}</Tag>
                    {item.message && <Text type="secondary" style={{ fontSize: 12 }}>{item.message}</Text>}
                  </Space>
                }
              />
              <div style={{ width: 150, textAlign: 'right' }}>
                <Progress
                  percent={item.progress || 0}
                  status={item.status === 'error' ? 'exception' : item.status === 'complete' ? 'success' : 'active'}
                  size="small"
                  showInfo={item.status !== 'pending'}
                />
                {item.items_saved !== undefined && item.status === 'complete' && (
                     <Text type="secondary" style={{ fontSize: 12, display: 'block' }}>
                         Saved: {item.items_saved}
                     </Text>
                )}
              </div>
            </List.Item>
          )}
        />
        <Divider style={{ margin: '16px 0', borderColor: '#f5f5f5' }}/>
        <Button onClick={() => setTasksToMonitor([])} disabled={!tasksToMonitor.some(t => t.status === 'complete' || t.status === 'error')} type="text">
            清除已完成/错误的任务
        </Button>
      </Drawer>

      {/* Analysis Modal */}
      {selectedNewsItemId !== null && (
        <AnalysisModal
          isOpen={analysisModalVisible}
          onClose={closeAnalysisModal}
          newsItemId={selectedNewsItemId}
        />
      )}
    </div>
  );
};

// Wrap the component with the HOC for authentication
export default withAuth(NewsPage);

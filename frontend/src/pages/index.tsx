import React, { useState, useEffect, useCallback } from 'react';
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
  message
} from 'antd';
import { 
  SearchOutlined,
  CalendarOutlined,
  TagOutlined,
  GlobalOutlined,
  ExperimentOutlined,
  DownloadOutlined,
  BarsOutlined
} from '@ant-design/icons';
import { NewsItem, NewsCategory, NewsSource, NewsFilterParams, FetchTaskItem } from '@/utils/types';
import * as newsService from '@/services/newsService';
import { handleApiError } from '@/utils/apiErrorHandler';
import Link from 'next/link';
import debounce from 'lodash/debounce';
import type { CheckboxChangeEvent } from 'antd/es/checkbox';

const { Title, Text, Paragraph } = Typography;
const { Option } = Select;

const NewsPage: React.FC = () => {
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

  // 加载新闻数据
  const loadNews = useCallback(async (params: NewsFilterParams) => {
    try {
      setLoading(true);
      setError(null);
      const newsData = await newsService.getNewsItems(params);
      setNews(newsData);
      setTotal(100);
    } catch (error) {
      handleApiError(error, '加载新闻失败');
      setError('无法加载新闻内容，请稍后再试');
    } finally {
      setLoading(false);
    }
  }, []);

  // 防抖搜索处理函数
  const debouncedSearch = useCallback(
    debounce((value: string) => {
      setFilters(prev => ({...prev, search_term: value, page: 1}));
    }, 500),
    []
  );

  // 处理过滤器变化
  const handleFilterChange = (key: keyof NewsFilterParams, value: any) => {
    setFilters(prev => {
      const updated = {...prev, [key]: value}; 
      // 当切换过滤条件时，重置页码
      if (key !== 'page') {
        updated.page = 1;
      }
      return updated;
    });
  };

  // 处理分类变化
  const handleCategoryChange = async (value: number | undefined) => {
    try {
      // 更新过滤器
      handleFilterChange('category_id', value);
      
      // 如果选择了分类，获取该分类的来源
      if (value !== undefined) {
        const sourcesData = await newsService.getSourcesByCategory(value);
        setSources(sourcesData);
      } else {
        // 如果选择"全部"，获取所有来源
        const sourcesData = await newsService.getSources();
        setSources(sourcesData);
      }
      
      // 重置来源过滤器
      handleFilterChange('source_id', undefined);
    } catch (error) {
      handleApiError(error, '无法更新分类的来源列表');
    }
  };

  // 加载初始数据
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
        handleApiError(error, '加载初始数据失败');
        setError('无法加载分类和来源数据，请刷新页面重试');
      } finally {
        setLoading(false);
      }
    };
    
    loadInitialData();
  }, []);

  // 监听过滤器变化加载新闻
  useEffect(() => {
    loadNews(filters);
  }, [filters, loadNews]);

  // 格式化日期显示
  const formatDate = (dateString?: string) => {
    if (!dateString) return '未知日期';
    const date = new Date(dateString);
    return date.toLocaleDateString('zh-CN');
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
  const handleFetchConfirm = () => {
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

    // Update the task list state (replace existing tasks for now)
    setTasksToMonitor(newTasks);

    // Close the settings modal
    setIsFetchModalVisible(false);

    // Inform the user
    message.success(`Added ${newTasks.length} fetch tasks. Click 'View Progress' to see them.`);

    // Reset selections in the settings modal for next time
    setSelectedSourceIds([]);
    setSelectedFetchCategory(undefined);
    setFilteredFetchSources(sources);
    setSelectAllSources(false);
    setIsIndeterminate(false);

    // -------------------------------------------------------------
    // TODO: Backend task triggering logic will be added here later.
    // Example: newTasks.forEach(task => triggerBackendFetch(task.sourceId));
    // -------------------------------------------------------------
  };

  // Helper function for status colors in task drawer
  const getStatusColor = (status: FetchTaskItem['status']) => {
    switch (status) {
      case 'pending': return 'default'; // Grey
      case 'fetching': return 'processing'; // Blue
      case 'complete': return 'success'; // Green
      case 'error': return 'error'; // Red
      default: return 'default';
    }
  };

  return (
    <div>
      {/* Action buttons (replacing the old title) */}
      <div style={{ marginBottom: 16 }}>
        <Space>
          <Button type="primary" icon={<DownloadOutlined />} onClick={showFetchModal}>
            Fetch News
          </Button>
          <Button icon={<BarsOutlined />} onClick={() => setIsTaskDrawerVisible(true)}>
            View Progress {tasksToMonitor.length > 0 ? `(${tasksToMonitor.length})` : ''}
          </Button>
        </Space>
      </div>
      
      {/* 过滤控件 */}
      <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
        <Col xs={24} sm={12} md={8} lg={6}>
          <Select
            placeholder="选择分类"
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
        <Col xs={24} sm={12} md={8} lg={6}>
          <Select
            placeholder="选择来源"
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
        <Col xs={24} sm={24} md={8} lg={12}>
          <Input
            placeholder="搜索新闻"
            prefix={<SearchOutlined />}
            onChange={(e) => debouncedSearch(e.target.value)}
            allowClear
          />
        </Col>
      </Row>
      
      {/* 错误提示 */}
      {error && (
        <Alert 
          message={error} 
          type="error" 
          showIcon 
          style={{ marginBottom: 16 }} 
        />
      )}
      
      {/* 加载状态 */}
      {loading ? (
        <div style={{ textAlign: 'center', padding: '50px 0' }}>
          <Spin size="large" tip="加载中..." />
        </div>
      ) : news.length === 0 ? (
        <Empty description="没有找到新闻" />
      ) : (
        <>
          {/* 新闻列表 */}
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
                <Card 
                  hoverable
                  cover={item.summary && (
                    <div style={{ height: 120, overflow: 'hidden', background: '#f5f5f5', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                      <Text ellipsis style={{ padding: 16 }}>{item.summary}</Text>
                    </div>
                  )}
                >
                  <Card.Meta
                    title={
                      <Link href={`/news/${item.id}`}>
                        <Text strong ellipsis style={{ height: 48 }}>
                          {item.title}
                        </Text>
                      </Link>
                    }
                    description={
                      <Space direction="vertical" size={0} style={{ width: '100%' }}>
                        <Space>
                          <GlobalOutlined />
                          <Text type="secondary">{item.source_name}</Text>
                        </Space>
                        <Space>
                          <TagOutlined />
                          <Text type="secondary">{item.category_name}</Text>
                        </Space>
                        <Space>
                          <CalendarOutlined />
                          <Text type="secondary">{formatDate(item.date)}</Text>
                        </Space>
                        <Divider style={{ margin: '8px 0' }} />
                        <div style={{ textAlign: 'right' }}>
                          <Button 
                            type="link" 
                            icon={<ExperimentOutlined />}
                            disabled={!item.analysis}
                          >
                            {item.analysis ? '查看分析' : '暂无分析'}
                          </Button>
                        </div>
                      </Space>
                    }
                  />
                </Card>
              </List.Item>
            )}
          />
          
          {/* 分页 */}
          <div style={{ textAlign: 'center', marginTop: 24 }}>
            <Pagination
              current={filters.page}
              pageSize={filters.page_size}
              total={total}
              onChange={(page) => handleFilterChange('page', page)}
              showSizeChanger
              onShowSizeChange={(_, size) => handleFilterChange('page_size', size)}
              showTotal={(total) => `共 ${total} 条`}
            />
          </div>
        </>
      )}

      {/* Fetch Settings Modal */}
      <Modal
        title="Fetch News Settings"
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
            <Form.Item label="Step 1: Filter News Category (Optional)">
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
                Select/Deselect All ({filteredFetchSources.length} sources in current list)
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
                  <Text type="secondary">Please select a category, no sources found in this category, or sources haven't loaded.</Text>
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
                description={<Tag color={getStatusColor(item.status)}>{item.status.toUpperCase()}</Tag>}
              />
              <div style={{ width: 150, textAlign: 'right' }}>
                <Progress
                  percent={item.progress || 0}
                  status={item.status === 'error' ? 'exception' : item.status === 'complete' ? 'success' : undefined}
                  size="small"
                />
                {item.status === 'error' && <Text type="danger" style={{ fontSize: '12px', display: 'block' }}>{item.message || 'Failed'}</Text>}
              </div>
            </List.Item>
          )}
        />
        {/* TODO: Implement real-time progress updates via WebSocket or polling here later */}
      </Drawer>
    </div>
  );
};

export default NewsPage; 
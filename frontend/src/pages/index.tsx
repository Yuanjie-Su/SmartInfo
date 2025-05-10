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
  Tooltip,
  DatePicker, // Keep if you plan to use it for history date selection
  Badge
} from 'antd';
import {
  SearchOutlined,
  CalendarOutlined,
  TagOutlined,
  GlobalOutlined,
  ExperimentOutlined,
  DownloadOutlined,
  BarsOutlined,
  LinkOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  StopOutlined,
  SyncOutlined,
  LoadingOutlined,
  HistoryOutlined,
  DeleteOutlined,
  ClockCircleOutlined
} from '@ant-design/icons';
import { NewsItem, NewsCategory, NewsSource, NewsFilterParams, FetchTaskItem, FetchHistoryItem } from '@/utils/types'; // Removed OverallStatusInfo
import * as newsService from '@/services/newsService';
import { handleApiError, extractErrorMessage } from '@/utils/apiErrorHandler'; // Import extractErrorMessage
import Link from 'next/link';
import debounce from 'lodash/debounce';
import type { CheckboxChangeEvent } from 'antd/es/checkbox';
import AnalysisModal from '@/components/analysis/AnalysisModal';
import withAuth from '@/components/auth/withAuth'; // Import the HOC
import dayjs from 'dayjs';

const { Title, Text, Paragraph } = Typography;
const { Option } = Select;

// Step codes enum - must match backend codes
enum TaskStep {
  Preparing = 1,
  Crawling = 2,
  ExtractingLinks = 3,
  Analyzing = 4,
  Saving = 5,
  Complete = 6,
  Error = 7,
  Skipped = 8,
}

// Helper to map step code to display string
const getStepDisplayString = (stepCode: TaskStep | number): string => {
  switch (stepCode) {
    case TaskStep.Preparing: return 'Preparing';
    case TaskStep.Crawling: return 'Crawling';
    case TaskStep.ExtractingLinks: return 'Extracting Links';
    case TaskStep.Analyzing: return 'Analyzing';
    case TaskStep.Saving: return 'Saving';
    case TaskStep.Complete: return 'Complete';
    case TaskStep.Error: return 'Error';
    case TaskStep.Skipped: return 'Skipped';
    default: return 'Unknown';
  }
};

const NewsPage: React.FC = () => {
  const { token } = useAuth();

  const [news, setNews] = useState<NewsItem[]>([]);
  const [categories, setCategories] = useState<NewsCategory[]>([]);
  const [sources, setSources] = useState<NewsSource[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<{ type: string, message: string, status?: number } | null>(null); // Updated error state type
  const [filters, setFilters] = useState<NewsFilterParams>({
    page: 1,
    page_size: 10,
    category_id: undefined,
    source_id: undefined,
    search_term: '',
    fetch_date: undefined, // Initialize new filter
    sort_by: undefined, // Initialize new filter
  });
  const [total, setTotal] = useState(0);

  const [isFetchModalVisible, setIsFetchModalVisible] = useState<boolean>(false);
  const [selectedFetchCategory, setSelectedFetchCategory] = useState<number | undefined>(undefined);
  const [filteredFetchSources, setFilteredFetchSources] = useState<NewsSource[]>([]);
  const [selectedSourceIds, setSelectedSourceIds] = useState<number[]>([]);
  const [selectAllSources, setSelectAllSources] = useState<boolean>(false);
  const [isIndeterminate, setIsIndeterminate] = useState<boolean>(false);

  const [isTaskDrawerVisible, setIsTaskDrawerVisible] = useState<boolean>(false);
  const [tasksToMonitor, setTasksToMonitor] = useState<FetchTaskItem[]>([]);
  // Removed overallTaskStatus state

  const [analysisModalVisible, setAnalysisModalVisible] = useState<boolean>(false);
  const [selectedNewsItemId, setSelectedNewsItemId] = useState<number | null>(null);

  const [taskGroupId, setTaskGroupId] = useState<string | null>(null);
  const wsRef = useRef<WebSocket | null>(null);

  const [todaysHistory, setTodaysHistory] = useState<FetchHistoryItem[]>([]);
  const [isHistoryLoading, setIsHistoryLoading] = useState<boolean>(false);
  const [historicalData, setHistoricalData] = useState<FetchHistoryItem[] | null>(null);
  const [viewingDate, setViewingDate] = useState<'today' | 'history'>('today');
  const [selectedHistoryDate, setSelectedHistoryDate] = useState<dayjs.Dayjs | null>(null);


  const loadNews = useCallback(async (params: NewsFilterParams) => {
    try {
      setLoading(true);
      setError(null); // Reset error state
      const newsData = await newsService.getNewsItems(params);
      setNews(newsData);
      // Assuming total is fetched with newsData or a separate call
      // For now, if newsData is an object with 'items' and 'total'
      if (newsData && typeof newsData === 'object' && 'items' in newsData && 'total' in newsData) {
        setNews((newsData as any).items);
        setTotal((newsData as any).total);
      } else if (Array.isArray(newsData)) { // Fallback if API returns just an array
        setNews(newsData);
        setTotal(newsData.length); // Or a default like 100 if pagination is not fully dynamic
      } else {
        setNews([]);
        setTotal(0);
      }
    } catch (err: any) { // Catch the error here
      console.error('Failed to load news:', err);
      const errorDetails = extractErrorMessage(err); // Use the structured error handler
      setError(errorDetails); // Set the structured error state
      // No need for global message here, component handles display
    } finally {
      setLoading(false);
    }
  }, []);

  const fetchTodaysHistory = useCallback(async () => {
    setIsHistoryLoading(true);
    try {
      const todayStr = dayjs().format('YYYY-MM-DD');
      const history = await newsService.getFetchHistory({ date: todayStr });
      setTodaysHistory(history);
    } catch (error) {
      handleApiError(error, "Failed to load today's fetch history");
      setTodaysHistory([]);
    } finally {
      setIsHistoryLoading(false);
    }
  }, []);

  const fetchHistoricalData = useCallback(async (date: string | null) => {
    if (!date) {
      setHistoricalData(null);
      return;
    }
    setIsHistoryLoading(true);
    setHistoricalData(null);
    try {
      const history = await newsService.getFetchHistory({ date });
      setHistoricalData(history);
    } catch (error) {
      handleApiError(error, `Failed to load fetch history for ${date}`);
    } finally {
      setIsHistoryLoading(false);
    }
  }, []);

  const debouncedSearch = useCallback(
    debounce((value: string) => {
      setFilters(prev => ({...prev, search_term: value, page: 1}));
    }, 500),
    []
  );

  const handleFilterChange = (key: keyof NewsFilterParams, value: any) => {
    setFilters(prev => {
      const updated = {...prev, [key]: value};
      if (key !== 'page') {
        updated.page = 1;
      }
      // Clear fetch_date and sort_by if other filters change, unless it's source_id or category_id
      if (key !== 'source_id' && key !== 'category_id' && key !== 'page' && key !== 'page_size' && key !== 'search_term') {
         updated.fetch_date = undefined;
         updated.sort_by = undefined;
      }
      return updated;
    });
  };

  const handleCategoryChange = async (value: number | undefined) => {
    try {
      handleFilterChange('category_id', value);
      if (value !== undefined) {
        const sourcesData = await newsService.getSourcesByCategory(value);
        setSources(sourcesData);
      } else {
        const sourcesData = await newsService.getSources();
        setSources(sourcesData);
      }
      handleFilterChange('source_id', undefined);
    } catch (error) {
      handleApiError(error, 'Cannot update source list for category');
    }
  };

  const connectWebSocket = useCallback((currentTaskGroupId: string) => {
    if (wsRef.current) {
      console.log('Closing previous WebSocket connection.');
      wsRef.current.close();
    }

    if (!token) {
      console.error('No authentication token available. Cannot establish WebSocket connection.');
      message.error('无法建立WebSocket连接：未登录或会话已过期');
      return;
    }

    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const apiUrlBase = (process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000').replace(/^http/, 'ws').replace(/\/$/, '');
    const wsUrl = `${apiUrlBase}/api/tasks/ws/tasks/group/${currentTaskGroupId}?token=${encodeURIComponent(token)}`;
    console.log('Connecting to WebSocket with auth token:', wsUrl);

    try {
        const ws = new WebSocket(wsUrl);
        wsRef.current = ws;

        ws.onopen = () => {
          console.log(`WebSocket connected for task group ID: ${currentTaskGroupId}`);
        };

        ws.onmessage = (event) => {
          try {
              const taskUpdate = JSON.parse(event.data);
              console.log('Received task update:', taskUpdate);

              if (taskUpdate.event === "batch_task_failed") {
                  console.log(`Batch Celery task ${taskUpdate.task_id} failed in group ${currentTaskGroupId}: ${taskUpdate.message}`);
                  if (taskUpdate.affected_source_ids && Array.isArray(taskUpdate.affected_source_ids)) {
                      setTasksToMonitor(prevTasks => prevTasks.map(task => {
                          if (taskUpdate.affected_source_ids.includes(task.sourceId) && (task.progress ?? 0) < 100) {
                              return { ...task, status: 'Error', progress: 100, message: 'Batch failed; this source did not complete.' };
                          }
                          return task;
                      }));
                  }
                  return;
              }

              if (taskUpdate.event === "overall_batch_completed") {
                  console.log(`Overall batch group ${currentTaskGroupId} has finished with status: ${taskUpdate.status}`);
                  // Removed setOverallTaskStatus
                  loadNews(filters);
                  fetchTodaysHistory(); // Refresh today's history after completion
                  setTimeout(() => {
                      if (wsRef.current) {
                          console.log('Closing WebSocket after overall completion event.');
                          wsRef.current.close();
                          wsRef.current = null;
                      }
                      setTaskGroupId(null);
                  }, 1000);
                  return;
              }

              if (taskUpdate.event === "source_progress" && taskUpdate.source_id !== undefined) {
                  setTasksToMonitor(prevTasks => {
                      const taskIndex = prevTasks.findIndex(t => t.sourceId === taskUpdate.source_id);
                      if (taskIndex === -1) {
                          console.warn(`Received update for source ID ${taskUpdate.source_id}, but task not found in monitor list.`);
                          return prevTasks;
                      }
                      const updatedTasks = [...prevTasks];
                      const taskToUpdate = { ...updatedTasks[taskIndex] };
                      taskToUpdate.status = getStepDisplayString(taskUpdate.step);
                      taskToUpdate.progress = taskUpdate.progress ?? taskToUpdate.progress;
                      if (taskUpdate.step === TaskStep.Error) {
                          taskToUpdate.error = true;
                      }
                      if (taskUpdate.items_saved !== undefined) {
                          taskToUpdate.items_saved = taskUpdate.items_saved;
                          taskToUpdate.items_saved_this_run = taskUpdate.items_saved; // Store for badge
                      }
                      if (taskUpdate.step === TaskStep.Error || taskUpdate.step === TaskStep.Skipped) {
                          taskToUpdate.progress = 100;
                      } else if (taskUpdate.step === TaskStep.Complete) {
                          taskToUpdate.progress = 100;
                      }
                      updatedTasks[taskIndex] = taskToUpdate;
                      return updatedTasks;
                  });
                  return;
              }
              console.log('Received unhandled WebSocket message:', taskUpdate);
          } catch (e) {
              console.error('Failed to parse or process WebSocket message:', e);
          }
        };

        ws.onerror = (error) => {
          console.error('WebSocket error:', error);
          message.error('WebSocket connection error.');
          wsRef.current = null;
          setTaskGroupId(null);
        };

        ws.onclose = (event) => {
          console.log(`WebSocket closed for task group ID: ${currentTaskGroupId}. Code: ${event.code}, Reason: ${event.reason}`);
          if (wsRef.current === ws) {
             wsRef.current = null;
          }
          // Do not reset taskGroupId here if closure was due to overall_batch_completed
          // as it's already reset in that handler.
        };
    } catch (err) {
        console.error("Failed to create WebSocket:", err);
        message.error("Failed to initialize WebSocket connection.");
    }
  }, [token, loadNews, filters, fetchTodaysHistory]);

  useEffect(() => {
    if (taskGroupId) {
      connectWebSocket(taskGroupId);
    }
    return () => {
      if (wsRef.current) {
        console.log('Closing WebSocket connection on cleanup (taskGroupId change or unmount).');
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, [taskGroupId, connectWebSocket]);

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
        setFilteredFetchSources(sourcesData);
        fetchTodaysHistory();
      } catch (err: any) { // Catch the error here
        console.error('Failed to load initial data:', err);
        const errorDetails = extractErrorMessage(err); // Use the structured error handler
        setError(errorDetails); // Set the structured error state
        // No need for global message here
      } finally {
        setLoading(false);
      }
    };
    loadInitialData();
  }, [fetchTodaysHistory]);

  useEffect(() => {
    loadNews(filters);
  }, [filters, loadNews]);

  const formatDate = (dateString?: string) => {
    if (!dateString) return 'Unknown date';
    return dayjs(dateString).format('YYYY-MM-DD'); // Consistent date format
  };

  const showFetchModal = () => {
    setSelectedFetchCategory(undefined);
    setFilteredFetchSources(sources);
    setSelectedSourceIds([]);
    setSelectAllSources(false);
    setIsIndeterminate(false);
    setIsFetchModalVisible(true);
  };

  const handleFetchCategoryChange = (value: number | undefined) => {
    setSelectedFetchCategory(value);
    const newFilteredSources = value === undefined ? sources : sources.filter(s => s.category_id === value);
    setFilteredFetchSources(newFilteredSources);
    setSelectedSourceIds([]);
    setSelectAllSources(false);
    setIsIndeterminate(false);
  };

  const handleSourceSelectionChange = (checkedValues: any[]) => {
    const numberValues = checkedValues as number[];
    setSelectedSourceIds(numberValues);
    const allVisibleSourceIds = filteredFetchSources.map(s => s.id);
    const allSelected = allVisibleSourceIds.length > 0 && numberValues.length === allVisibleSourceIds.length;
    const indeterminate = numberValues.length > 0 && numberValues.length < allVisibleSourceIds.length;
    setSelectAllSources(allSelected);
    setIsIndeterminate(indeterminate);
  };

  const handleSelectAllChange = (e: CheckboxChangeEvent) => {
    const isChecked = e.target.checked;
    const allVisibleSourceIds = filteredFetchSources.map(s => s.id);
    setSelectedSourceIds(isChecked ? allVisibleSourceIds : []);
    setSelectAllSources(isChecked);
    setIsIndeterminate(false);
  };

  const handleFetchConfirm = async () => {
    if (selectedSourceIds.length === 0) {
      message.warning('Please select at least one news source.');
      return;
    }

    const selectedSourcesDetails = sources.filter(s => selectedSourceIds.includes(s.id));
    const newTasks: FetchTaskItem[] = selectedSourcesDetails.map(source => ({
      sourceId: source.id,
      sourceName: source.name,
      status: 'Pending',
      progress: 0,
    }));

    // Removed setOverallTaskStatus(null)
    // Clear only non-pending/non-running tasks from monitor before adding new ones
    setTasksToMonitor(prevTasks => [
        ...prevTasks.filter(t => t.status !== 'Complete' && t.status !== 'Error' && t.status !== 'Skipped'),
        ...newTasks
    ]);

    setViewingDate('today');
    setHistoricalData(null);
    fetchTodaysHistory();

    setIsFetchModalVisible(false);
    setIsTaskDrawerVisible(true);

    try {
      const response = await newsService.fetchNewsFromSourcesBatchGroup(selectedSourceIds);
      const newGroupId = response.task_group_id;
      setTaskGroupId(newGroupId);
    } catch (error) {
      handleApiError(error, 'Failed to start news fetch tasks');
      setTasksToMonitor(prevTasks => prevTasks.filter(task => !selectedSourceIds.includes(task.sourceId)));
    } finally {
      setSelectedSourceIds([]);
      setSelectedFetchCategory(undefined);
      setFilteredFetchSources(sources);
      setSelectAllSources(false);
      setIsIndeterminate(false);
    }
  };

  const openAnalysisModal = (newsItemId: number) => {
    setSelectedNewsItemId(newsItemId);
    setAnalysisModalVisible(true);
  };

  const closeAnalysisModal = () => {
    setAnalysisModalVisible(false);
    setSelectedNewsItemId(null);
  };

  const getDisplayedTasks = () => {
    let displayed: (FetchTaskItem | FetchHistoryItem)[] = [];
    const processedSourceIds = new Set<number>();

    tasksToMonitor.forEach(task => {
      // Add all monitored tasks, their status will determine rendering
      displayed.push(task);
      processedSourceIds.add(task.sourceId);
    });

    if (viewingDate === 'today') {
      todaysHistory.forEach(hist => {
        if (!processedSourceIds.has(hist.source_id)) {
          displayed.push(hist);
          // processedSourceIds.add(hist.source_id); // Not strictly needed if only adding non-duplicates
        }
      });
    } else if (historicalData) {
      // When viewing history, only show historical data, not live tasks
      displayed = [...historicalData];
    }

    displayed.sort((a, b) => {
        const isALive = 'progress' in a && a.status !== 'Complete' && a.status !== 'Error' && a.status !== 'Skipped';
        const isBLive = 'progress' in b && b.status !== 'Complete' && b.status !== 'Error' && b.status !== 'Skipped';

        if (isALive && !isBLive) return -1;
        if (!isALive && isBLive) return 1;

        const timeA = 'last_updated_at' in a && a.last_updated_at ? new Date(a.last_updated_at).getTime() : ('sourceId' in a ? Date.now() : 0);
        const timeB = 'last_updated_at' in b && b.last_updated_at ? new Date(b.last_updated_at).getTime() : ('sourceId' in b ? Date.now() : 0);

        return timeB - timeA;
    });

    return displayed;
  };

  const displayedTasks = getDisplayedTasks();

  const getSourceId = (item: FetchTaskItem | FetchHistoryItem): number => {
    return 'sourceId' in item ? item.sourceId : item.source_id;
  };

  const getSourceName = (item: FetchTaskItem | FetchHistoryItem): string => {
    return 'sourceName' in item ? item.sourceName : item.source_name;
  };

  const getStatus = (item: FetchTaskItem | FetchHistoryItem): string => {
    if ('status' in item) return item.status;
    return 'Complete'; // FetchHistoryItem is always complete
  };

  const getProgress = (item: FetchTaskItem | FetchHistoryItem): number => {
    if ('progress' in item) return item.progress || 0;
    return 100; // FetchHistoryItem is always 100%
  };

  const getItemsSavedThisRun = (item: FetchTaskItem | FetchHistoryItem): number | undefined => {
    if ('items_saved_this_run' in item) return item.items_saved_this_run; // From live task
    if ('items_saved_today' in item) return item.items_saved_today; // From history item
    return undefined;
  };

  const handleHistoryDateChange = (date: dayjs.Dayjs | null, dateString: string | string[]) => {
    setSelectedHistoryDate(date);
    if (dateString && typeof dateString === 'string') {
      fetchHistoricalData(dateString);
    } else if (Array.isArray(dateString) && dateString.length > 0) {
      fetchHistoricalData(dateString[0]);
    } else {
      setHistoricalData(null); // Clear if date is cleared
    }
  };

  // Handler for clicking the "Saved Items" badge
  const handleTaskBadgeClick = (sourceId: number, fetchDate: string) => {
    console.log(`Badge clicked for source ${sourceId} on date ${fetchDate}`);
    setFilters(prevFilters => ({
      ...prevFilters, // Retain essential non-conflicting filters like page_size
      source_id: sourceId,
      fetch_date: fetchDate,     // New: Filter by the specific fetch date
      category_id: undefined,    // Clear other filters to focus on this source/date
      search_term: '',
      analyzed: undefined,
      page: 1,                   // Always reset to page 1 for new filter context
      sort_by: 'created_at_desc' // New: Sort by creation time
    }));
    setIsTaskDrawerVisible(false); // Close the drawer
    // Optional: window.scrollTo(0, 0); // Scroll to top
  };


  return (
    <div>
      <Row gutter={[16, 16]} style={{ marginBottom: 24 }} align="middle">
        <Col xs={24} sm={12} md={5} lg={5}>
          <Select
            placeholder="Select category"
            style={{ width: '100%' }}
            allowClear
            onChange={(value) => handleCategoryChange(value)}
            loading={loading && categories.length === 0}
            value={filters.category_id}
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
            loading={loading && sources.length === 0 && !!filters.category_id} // Only show loading if category is selected
            value={filters.source_id}
            disabled={!filters.category_id && sources.every(s => s.category_id !== undefined)} // Disable if no category selected and sources are category-specific
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
          <Button icon={<BarsOutlined />} onClick={() => {
              setViewingDate('today');
              fetchTodaysHistory();
              setIsTaskDrawerVisible(true);
            }} style={{ width: '100%' }}>
            Progress {tasksToMonitor.filter(t => t.status !== 'Complete' && t.status !== 'Error' && t.status !== 'Skipped').length > 0 ? `(${tasksToMonitor.filter(t => t.status !== 'Complete' && t.status !== 'Error' && t.status !== 'Skipped').length})` : ''}
          </Button>
        </Col>
      </Row>

      {error && (
        <Alert
          message={error.message || "An unexpected error occurred."}
          type="error"
          showIcon
          style={{ marginBottom: 16 }}
        />
      )}

      {loading && news.length === 0 ? ( // Show loading spinner only if news is empty
        <div style={{ textAlign: 'center', padding: '50px 0' }}>
          <Spin size="large" tip="Loading news..." />
        </div>
      ) : error ? ( // Check for any error
        error.type === 'notFound' ? ( // Specific Not Found UI
          <Empty description={error.message || "Content not found."} />
        ) : error.type === 'forbidden' ? ( // Specific Forbidden UI
          <Alert
            message="Access Denied"
            description={error.message || "You do not have permission to view this content."}
            type="error"
            showIcon
            style={{ marginBottom: 16 }}
          />
        ) : ( // Generic Error Alert
          <Alert
            message={error.message || "An unexpected error occurred."}
            type="error"
            showIcon
            style={{ marginBottom: 16 }}
          />
        )
      ) : !loading && news.length === 0 ? ( // Show empty state only if not loading, no error, and news is empty
        <Empty description="No news found. Try adjusting filters or fetching new articles." />
      ) : (
        <>
          <List
            grid={{ gutter: 16, xs: 1, sm: 1, md: 2, lg: 3, xl: 3, xxl: 4 }}
            dataSource={news}
            loading={loading && news.length > 0} // Show list loading indicator if news already exists
            renderItem={(item) => (
              <List.Item>
                <Card hoverable>
                  <Card.Meta
                    title={
                      <Tooltip title={item.title} placement="topLeft">
                        <Text strong style={{ fontSize: '16px', display: 'block', lineHeight: '1.4', maxHeight: '2.8em', overflow: 'hidden' }}>
                          {item.title}
                        </Text>
                      </Tooltip>
                    }
                    description={
                      <Space direction="vertical" size={12} style={{ width: '100%' }}>
                        <Space size={12} wrap>
                          <Space size={4}><CalendarOutlined style={{ color: 'var(--text-secondary)' }} /><Text type="secondary" style={{ fontSize: 12 }}>{formatDate(item.date)}</Text></Space>
                          <Space size={4}><GlobalOutlined style={{ color: 'var(--text-secondary)' }} /><Text type="secondary" style={{ fontSize: 12 }}>{item.source_name}</Text></Space>
                          <Space size={4}><TagOutlined style={{ color: 'var(--text-secondary)' }} /><Text type="secondary" style={{ fontSize: 12 }}>{item.category_name}</Text></Space>
                          {item.url && (
                            <Tooltip title="View Original">
                              <a href={item.url} target="_blank" rel="noopener noreferrer" style={{ color: 'var(--accent-color)', display: 'inline-flex', alignItems: 'center' }}>
                                <LinkOutlined />
                              </a>
                            </Tooltip>
                          )}
                        </Space>
                        {item.summary && (
                          <Tooltip title={item.summary} placement="bottomLeft">
                            <Paragraph ellipsis={{ rows: 3 }} style={{ marginBottom: 0, color: 'var(--text-secondary)', minHeight: '60px' }}>
                              {item.summary}
                            </Paragraph>
                          </Tooltip>
                        )}
                        <div style={{ textAlign: 'right', paddingTop: 8 }}>
                          <Tooltip title="Analyze News">
                            <Button type="text" icon={<ExperimentOutlined style={{color: 'var(--accent-color)'}}/>} onClick={() => openAnalysisModal(item.id)} />
                          </Tooltip>
                        </div>
                      </Space>
                    }
                  />
                </Card>
              </List.Item>
            )}
          />
          <div style={{ textAlign: 'center', marginTop: 24, display: 'flex', justifyContent: 'center' }}>
            <Pagination
              current={filters.page}
              pageSize={filters.page_size}
              total={total}
              onChange={(page) => handleFilterChange('page', page)}
              showSizeChanger
              onShowSizeChange={(_, size) => {
                handleFilterChange('page_size', size);
                handleFilterChange('page', 1); // Reset to page 1 on size change
              }}
              showTotal={(totalItems, range) => `${range[0]}-${range[1]} of ${totalItems} items`}
            />
          </div>
        </>
      )}

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
                  <Text type="secondary">No sources found for this filter or sources are not yet loaded.</Text>
                )}
              </div>
            </Form.Item>
          </Form>
        </Spin>
      </Modal>

      <Drawer
        title="Task Progress"
        placement="right"
        width={350}
        onClose={() => setIsTaskDrawerVisible(false)}
        open={isTaskDrawerVisible}
        mask={false}
        closable={true}
        footer={
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', width: '100%' }}>
            <Tooltip title="Clear Completed & Errored Tasks">
              <Button
                onClick={() => {
                  setTasksToMonitor(prev => prev.filter(t =>
                    t.status !== 'Complete' && t.status !== 'Error' && t.status !== 'Skipped'
                  ));
                  // Removed setOverallTaskStatus(null)
                }}
                disabled={!tasksToMonitor.some(t =>
                  t.status === 'Complete' || t.status === 'Error' || t.status === 'Skipped'
                )} // Updated disabled condition
                type="text"
                icon={<DeleteOutlined />}
              />
            </Tooltip>

            {viewingDate === 'today' ? (
              <Tooltip title="View History">
                <Button
                  type="text"
                  icon={<HistoryOutlined />}
                  onClick={() => {
                    setViewingDate('history');
                    setSelectedHistoryDate(null); // Reset selected date
                    setHistoricalData(null); // Clear previous historical data
                    // Optionally fetch for a default date like yesterday:
                    // const yesterday = dayjs().subtract(1, 'day');
                    // setSelectedHistoryDate(yesterday);
                    // fetchHistoricalData(yesterday.format('YYYY-MM-DD'));
                  }}
                />
              </Tooltip>
            ) : (
              <Tooltip title="View Today's Progress">
                <Button
                  type="text"
                  icon={<ClockCircleOutlined />}
                  onClick={() => {
                    setViewingDate('today');
                    fetchTodaysHistory(); // Refresh today's data
                    setHistoricalData(null); // Clear historical data
                    setSelectedHistoryDate(null); // Clear selected history date
                  }}
                />
              </Tooltip>
            )}
          </div>
        }
      >
        {/* Removed overallTaskStatus display block */}

        {viewingDate === 'history' && (
          <div style={{ marginBottom: 16 }}>
            <DatePicker
              value={selectedHistoryDate}
              onChange={handleHistoryDateChange}
              style={{ width: '100%' }}
              disabledDate={(current) => current && current > dayjs().endOf('day')}
            />
          </div>
        )}

        {(isHistoryLoading && (viewingDate === 'history' || (viewingDate === 'today' && todaysHistory.length === 0 && tasksToMonitor.length === 0))) ? (
            <div style={{ textAlign: 'center', padding: '20px 0' }}><Spin tip="Loading history..." /></div>
        ) : displayedTasks.length === 0 ? (
            <Empty description={viewingDate === 'history' && !selectedHistoryDate ? "Select a date to view history." : "No tasks or history to display."} />
        ) : (
            <List
            itemLayout="horizontal"
            dataSource={displayedTasks}
            renderItem={(item: FetchTaskItem | FetchHistoryItem, index) => {
                const itemStatus = getStatus(item);
                const itemsSaved = getItemsSavedThisRun(item);
                const itemProgress = getProgress(item);
                const isRunningOrPending = itemStatus !== 'Complete' && itemStatus !== 'Error' && itemStatus !== 'Skipped';

                const isLastRunningTask = isRunningOrPending &&
                (index === displayedTasks.length - 1 || !('progress' in displayedTasks[index+1] && getStatus(displayedTasks[index+1]) !== 'Complete' && getStatus(displayedTasks[index+1]) !== 'Error' && getStatus(displayedTasks[index+1]) !== 'Skipped'));

                let extraContent = null;
                const iconStyle = { fontSize: '16px', verticalAlign: 'middle' };
                const badgeAreaStyle = {
                    minWidth: '45px', // Adjusted for potential 3-digit numbers
                    display: 'inline-block',
                    textAlign: 'left' as 'left',
                    verticalAlign: 'middle',
                    marginLeft: '8px' // Space between icon and badge area
                };

                const sourceId = getSourceId(item);
                let determinedFetchDate: string;

                if ('progress' in item && item.status !== 'Complete' && item.status !== 'Error' && item.status !== 'Skipped') {
                    // For live/pending tasks, or tasks that just completed in this session
                    determinedFetchDate = dayjs().format('YYYY-MM-DD');
                } else if ('record_date' in item && item.record_date) { // For historical items
                    determinedFetchDate = dayjs(item.record_date).format('YYYY-MM-DD');
                } else {
                    // Fallback for tasks that just completed and might not have record_date yet in displayedTasks
                    // but are not "live" anymore. This assumes completion implies "today" for the click.
                    determinedFetchDate = dayjs().format('YYYY-MM-DD');
                }


                if (isRunningOrPending) {
                extraContent = (
                    <Space align="center">
                    <Tooltip title={itemStatus}>
                        {itemStatus === 'Preparing' || itemStatus === 'Pending' ? (
                        <SyncOutlined spin style={{ ...iconStyle, color: '#1890ff' }} />
                        ) : (
                        <LoadingOutlined style={{ ...iconStyle, color: '#1890ff' }} />
                        )}
                    </Tooltip>
                    <Progress
                        percent={itemProgress}
                        status="active"
                        size="small"
                        showInfo={false}
                        style={{ width: 60 }} // Reduced width for progress
                    />
                    </Space>
                );
                } else if (itemStatus === 'Complete') {
                extraContent = (
                    <Space align="center" size={0}>
                    <Tooltip title="Complete">
                        <CheckCircleOutlined style={{ ...iconStyle, color: '#52c41a' }} />
                    </Tooltip>
                    <div style={{...badgeAreaStyle, cursor: 'pointer'}} onClick={() => handleTaskBadgeClick(sourceId, determinedFetchDate)}>
                        {itemsSaved !== undefined && itemsSaved > 0 && (
                        <Badge count={`+${itemsSaved}`} style={{ backgroundColor: '#52c41a' }} size="small" />
                        )}
                    </div>
                    </Space>
                );
                } else if (itemStatus === 'Error') {
                extraContent = (
                    <Space align="center" size={0}>
                    <Tooltip title="Error">
                        <CloseCircleOutlined style={{ ...iconStyle, color: '#f5222d' }} />
                    </Tooltip>
                    <div style={badgeAreaStyle} />
                    </Space>
                );
                } else if (itemStatus === 'Skipped') {
                extraContent = (
                    <Space align="center" size={0}>
                    <Tooltip title="Skipped">
                        <StopOutlined style={{ ...iconStyle, color: '#faad14' }} />
                    </Tooltip>
                    <div style={badgeAreaStyle} />
                    </Space>
                );
                }

                return (
                <>
                    <List.Item
                    key={`${getSourceId(item)}-${'sourceId' in item ? 'live' : 'hist'}-${index}`} // More unique key
                    extra={extraContent}
                    >
                    <List.Item.Meta
                        title={<Text ellipsis={{tooltip: getSourceName(item)}}>{getSourceName(item)}</Text>}
                        description={ viewingDate === 'history' && 'last_updated_at' in item && item.last_updated_at ?
                            <Text type="secondary" style={{fontSize: '12px'}}>{dayjs(item.last_updated_at).format('HH:mm:ss')}</Text>
                            : null
                        }
                    />
                    </List.Item>

                    {isLastRunningTask && viewingDate === 'today' && <Divider style={{ margin: '8px 0' }} />}
                </>
                );
            }}
            />
        )}
      </Drawer>

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

export default withAuth(NewsPage);

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
  Divider
} from 'antd';
import { 
  SearchOutlined,
  CalendarOutlined,
  TagOutlined,
  GlobalOutlined,
  ExperimentOutlined
} from '@ant-design/icons';
import { News, NewsCategory, NewsSource, NewsFilterParams } from '@/utils/types';
import * as newsService from '@/services/newsService';
import { handleApiError } from '@/utils/apiErrorHandler';
import Link from 'next/link';
import debounce from 'lodash/debounce';

const { Title, Text, Paragraph } = Typography;
const { Option } = Select;

const NewsPage: React.FC = () => {
  // State
  const [news, setNews] = useState<News[]>([]);
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
  const [total, setTotal] = useState(0); // 总条目数，用于分页

  // 加载新闻数据
  const loadNews = useCallback(async (params: NewsFilterParams) => {
    try {
      setLoading(true);
      setError(null);
      const newsData = await newsService.getNews(params);
      setNews(newsData);
      // 假设API返回的是全部数据，暂时设置一个固定总数
      // 实际情况中，API应该返回总数
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
        const sourcesData = await newsService.getSources(value);
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

  return (
    <div>
      <Title level={2}>新闻列表</Title>
      
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
    </div>
  );
};

export default NewsPage; 
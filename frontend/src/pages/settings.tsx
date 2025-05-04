import React, { useState, useEffect } from 'react';
import { 
  Typography, 
  Tabs, 
  Form, 
  Input, 
  Button, 
  Table, 
  Space, 
  Popconfirm,
  Modal,
  message,
  Card,
  Divider,
  Switch,
  Select,
  Spin,
  Alert,
  InputNumber,
  Tag
} from 'antd';
import { 
  EditOutlined, 
  DeleteOutlined, 
  PlusOutlined,
  ReloadOutlined,
  KeyOutlined,
  ApiOutlined,
  SettingOutlined,
  SaveOutlined
} from '@ant-design/icons';
import type { TableProps } from 'antd/lib/table';
import { ApiKey, NewsCategory, NewsSource } from '@/utils/types';
import * as settingsService from '@/services/settingsService';
import * as newsService from '@/services/newsService';
import MainLayout from '../components/layout/MainLayout';
import { handleApiError } from '../utils/apiErrorHandler';

const { Title, Text, Paragraph } = Typography;
const { TabPane } = Tabs;
const { Option } = Select;

// API Key form modal
interface ApiKeyFormValues {
  model: string;
  base_url: string;
  api_key: string;
  context: number;
  max_output_tokens: number;
  description?: string;
}

const Settings: React.FC = () => {
  // State
  const [settings, setSettings] = useState<Record<string, any>>({});
  const [apiKeys, setApiKeys] = useState<ApiKey[]>([]);
  const [categories, setCategories] = useState<NewsCategory[]>([]);
  const [sources, setSources] = useState<NewsSource[]>([]);
  const [loading, setLoading] = useState(false);
  const [savingSettings, setSavingSettings] = useState(false);
  const [settingsLoading, setSettingsLoading] = useState(true);
  const [apiKeysLoading, setApiKeysLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  
  // API Key modal state
  const [isApiKeyModalVisible, setIsApiKeyModalVisible] = useState(false);
  const [apiKeyForm] = Form.useForm<ApiKeyFormValues>();
  const [editingApiKeyId, setEditingApiKeyId] = useState<number | null>(null);
  const [editingApiKey, setEditingApiKey] = useState<ApiKey | null>(null);
  
  // Source modal state
  const [isSourceModalVisible, setIsSourceModalVisible] = useState(false);
  const [sourceForm] = Form.useForm<{ name: string; url: string; category_id: number }>();
  const [editingSourceId, setEditingSourceId] = useState<number | null>(null);
  const [newCategoryName, setNewCategoryName] = useState<string>('');
  const [isAddCategoryModalVisible, setIsAddCategoryModalVisible] = useState(false);
  
  // Settings form
  const [settingsForm] = Form.useForm();
  
  // Load initial data
  useEffect(() => {
    loadAllData();
  }, []);
  
  const loadAllData = async () => {
    try {
      setLoading(true);
      await Promise.all([
        loadSettings(),
        loadApiKeys(),
        loadCategories(),
        loadSources()
      ]);
    } catch (error) {
      console.error('Failed to load settings data:', error);
      message.error('Failed to load settings data');
    } finally {
      setLoading(false);
    }
  };
  
  const loadSettings = async () => {
    try {
      setSettingsLoading(true);
      const settingsData = await settingsService.getSettings();
      setSettings(settingsData);
      settingsForm.setFieldsValue(settingsData);
    } catch (err) {
      handleApiError(err, '加载设置失败');
      setError('加载设置失败');
    } finally {
      setSettingsLoading(false);
    }
  };
  
  const loadApiKeys = async () => {
    try {
      setApiKeysLoading(true);
      const apiKeysData = await settingsService.getApiKeys();
      setApiKeys(apiKeysData);
    } catch (err) {
      handleApiError(err, '加载API密钥失败');
      setError('加载API密钥失败');
    } finally {
      setApiKeysLoading(false);
    }
  };
  
  const loadCategories = async () => {
    const categoriesData = await newsService.getCategories();
    setCategories(categoriesData);
  };
  
  const loadSources = async () => {
    const sourcesData = await newsService.getSources();
    setSources(sourcesData);
  };
  
  // Settings management
  const handleSettingChange = (key: string, value: any) => {
    setSettings(prev => ({
      ...prev,
      [key]: value
    }));
  };
  
  const saveSettings = async (values: Record<string, any>) => {
    try {
      setSavingSettings(true);
      const result = await settingsService.updateSettings(values);
      setSettings(result.settings);
      message.success('设置保存成功');
    } catch (error) {
      handleApiError(error, '保存设置失败');
    } finally {
      setSavingSettings(false);
    }
  };
  
  const resetSettings = async () => {
    try {
      setLoading(true);
      const result = await settingsService.resetSettings();
      setSettings(result.settings);
      settingsForm.setFieldsValue(result.settings);
      message.success('设置已重置为默认值');
    } catch (error) {
      handleApiError(error, '重置设置失败');
    } finally {
      setLoading(false);
    }
  };
  
  // API Key management
  const showAddApiKeyModal = () => {
    apiKeyForm.resetFields();
    setEditingApiKey(null);
    setEditingApiKeyId(null);
    setIsApiKeyModalVisible(true);
  };
  
  const showEditApiKeyModal = (record: ApiKey) => {
    setEditingApiKey(record);
    setEditingApiKeyId(record.id);
    
    // Fetch the API key details including the actual key value
    settingsService.getApiKey(record.id)
      .then(apiKeyData => {
        apiKeyForm.setFieldsValue({
          model: apiKeyData.model,
          base_url: apiKeyData.base_url,
          api_key: apiKeyData.api_key, // Pre-fill with actual API key
          context: apiKeyData.context,
          max_output_tokens: apiKeyData.max_output_tokens,
          description: apiKeyData.description
        });
        setIsApiKeyModalVisible(true);
      })
      .catch(error => {
        handleApiError(error, '加载API密钥详情失败');
      });
  };
  
  const handleApiKeySave = async () => {
    try {
      const values = await apiKeyForm.validateFields();
      
      if (editingApiKey) {
        // Update existing
        await settingsService.updateApiKey(editingApiKeyId!, values);
        message.success('API密钥更新成功');
      } else {
        // Create new
        await settingsService.createApiKey(values);
        message.success('API密钥创建成功');
      }
      
      setIsApiKeyModalVisible(false);
      loadApiKeys();
    } catch (error) {
      handleApiError(error, '保存API密钥失败');
    }
  };
  
  const handleDeleteApiKey = async (apiKeyId: number) => {
    try {
      await settingsService.deleteApiKey(apiKeyId);
      message.success('API密钥删除成功');
      loadApiKeys();
    } catch (error) {
      handleApiError(error, '删除API密钥失败');
    }
  };
  
  // Add test API key function
  const handleTestApiKey = async (apiKeyId: number) => {
    const testMessage = message.loading('正在测试API密钥连接...', 0);
    
    try {
      const result = await settingsService.testApiKey(apiKeyId);
      testMessage();
      
      if (result.status === 'success') {
        message.success('连接测试成功！');
      } else {
        message.error(`测试失败: ${result.message}`);
      }
    } catch (error) {
      testMessage();
      handleApiError(error, '测试API密钥失败');
    }
  };
  
  // Source management
  const showAddSourceModal = () => {
    sourceForm.resetFields();
    setEditingSourceId(null);
    setIsSourceModalVisible(true);
  };
  
  const showEditSourceModal = (record: NewsSource) => {
    sourceForm.setFieldsValue({
      name: record.name,
      url: record.url,
      category_id: record.category_id
    });
    setEditingSourceId(record.id);
    setIsSourceModalVisible(true);
  };
  
  const handleSourceSave = async () => {
    try {
      const values = await sourceForm.validateFields();
      
      if (editingSourceId) {
        // Update existing
        await newsService.updateSource(editingSourceId, values);
        message.success('Source updated successfully');
      } else {
        // Create new
        await newsService.createSource(values);
        message.success('Source created successfully');
      }
      
      setIsSourceModalVisible(false);
      loadSources();
    } catch (error) {
      console.error('Failed to save source:', error);
      message.error('Failed to save source');
    }
  };
  
  const handleDeleteSource = async (id: number) => {
    try {
      await newsService.deleteSource(id);
      message.success('Source deleted successfully');
      loadSources();
    } catch (error) {
      console.error('Failed to delete source:', error);
      message.error('Failed to delete source');
    }
  };
  
  // Category management
  const handleAddCategoryClick = () => {
    setNewCategoryName('');
    setIsAddCategoryModalVisible(true);
  };
  
  const handleCreateCategory = async () => {
    if (!newCategoryName.trim()) {
      message.error('类别名称不能为空');
      return;
    }
    
    try {
      const newCategory = await newsService.createCategory({ name: newCategoryName });
      message.success('类别创建成功');
      await loadCategories();
      setIsAddCategoryModalVisible(false);
      
      // Optionally select the new category in the form
      sourceForm.setFieldsValue({ category_id: newCategory.id });
    } catch (error) {
      handleApiError(error, '创建类别失败');
    }
  };
  
  const handleDeleteCategoryTag = (categoryId: number) => {
    Modal.confirm({
      title: '确认删除',
      content: '确定要删除此类别吗？删除后无法恢复。',
      okText: '删除',
      cancelText: '取消',
      okType: 'danger',
      onOk: async () => {
        try {
          await newsService.deleteCategory(categoryId);
          message.success('类别删除成功');
          await loadCategories();
        } catch (error) {
          handleApiError(error, '删除类别失败');
        }
      }
    });
  };
  
  // API Key columns
  const apiKeyColumns: TableProps<ApiKey>['columns'] = [
    {
      title: '模型',
      dataIndex: 'model',
      key: 'model',
    },
    {
      title: 'API密钥',
      key: 'api_key',
      render: () => '••••••••',
    },
    {
      title: '上下文长度',
      dataIndex: 'context',
      key: 'context',
    },
    {
      title: '最大输出Token',
      dataIndex: 'max_output_tokens',
      key: 'max_output_tokens',
    },
    {
      title: '创建时间',
      dataIndex: 'created_date',
      key: 'created_date',
      render: (date?: string) => date ? new Date(date).toLocaleString() : '-', // Use ISO string directly
    },
    {
      title: '说明',
      dataIndex: 'description',
      key: 'description',
    },
    {
      title: '操作',
      key: 'action',
      render: (_: any, record: ApiKey) => (
        <Space>
          <Button 
            icon={<EditOutlined />} 
            onClick={() => showEditApiKeyModal(record)}
            size="small"
          >
            编辑
          </Button>
          <Button
            onClick={() => handleTestApiKey(record.id)}
            size="small"
          >
            测试
          </Button>
          <Popconfirm
            title="确定要删除此API密钥吗？"
            onConfirm={() => handleDeleteApiKey(record.id)}
            okText="是"
            cancelText="否"
          >
            <Button 
              danger
              icon={<DeleteOutlined />}
              size="small"
            >
              删除
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];
  
  const sourceColumns: TableProps<NewsSource>['columns'] = [
    {
      title: '名称',
      dataIndex: 'name',
      key: 'name',
    },
    {
      title: 'URL',
      dataIndex: 'url',
      key: 'url',
      render: (text) => <a href={text} target="_blank" rel="noopener noreferrer">{text}</a>,
    },
    {
      title: '类别',
      dataIndex: 'category',
      key: 'category',
      render: (_, record) => {
        const category = categories.find(c => c.id === record.category_id);
        return category ? category.name : '-';
      },
    },
    {
      title: '操作',
      key: 'actions',
      render: (_: any, record: NewsSource) => (
        <Space>
          <Button 
            icon={<EditOutlined />} 
            onClick={() => showEditSourceModal(record)}
            size="small"
          >
            编辑
          </Button>
          <Popconfirm
            title="确定要删除此来源吗？"
            onConfirm={() => handleDeleteSource(record.id)}
            okText="是"
            cancelText="否"
          >
            <Button 
              danger 
              icon={<DeleteOutlined />}
              size="small"
            >
              删除
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];
  
  return (
    <MainLayout>
      <div style={{ padding: '24px' }}>
        <Title level={2}>系统设置</Title>
        
        {error && <Alert message={error} type="error" style={{ marginBottom: 16 }} />}
        
        <Tabs defaultActiveKey="general">
          <TabPane 
            tab={<><SettingOutlined /> 通用设置</>} 
            key="general"
          >
            <Card title="应用程序设置" extra={
              <Space>
                <Button 
                  icon={<ReloadOutlined />} 
                  onClick={resetSettings}
                >
                  重置为默认
                </Button>
              </Space>
            }>
              <Spin spinning={settingsLoading}>
                <Form
                  form={settingsForm}
                  layout="vertical"
                  onFinish={saveSettings}
                >
                  {Object.entries(settings).map(([key, value]) => (
                    <Form.Item 
                      key={key} 
                      name={key}
                      label={key.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())}
                    >
                      <Input />
                    </Form.Item>
                  ))}
                  
                  <Form.Item>
                    <Button type="primary" htmlType="submit" loading={savingSettings} icon={<SaveOutlined />}>
                      保存设置
                    </Button>
                  </Form.Item>
                </Form>
              </Spin>
            </Card>
          </TabPane>
          
          <TabPane 
            tab={<><KeyOutlined /> API密钥</>} 
            key="api-keys"
          >
            <div style={{ marginBottom: 16 }}>
              <Button 
                type="primary" 
                icon={<PlusOutlined />} 
                onClick={showAddApiKeyModal}
              >
                添加API密钥
              </Button>
            </div>
            
            <Spin spinning={apiKeysLoading}>
              <Table 
                dataSource={apiKeys} 
                columns={apiKeyColumns} 
                rowKey="id"
                pagination={false}
              />
            </Spin>
          </TabPane>
          
          <TabPane 
            tab={<><ApiOutlined /> 新闻来源</>} 
            key="sources"
          >
            <div style={{ marginBottom: 16 }}>
              <Button 
                type="primary" 
                icon={<PlusOutlined />} 
                onClick={showAddSourceModal}
              >
                添加来源
              </Button>
            </div>
            
            <Table 
              dataSource={sources} 
              columns={[
                {
                  title: '名称',
                  dataIndex: 'name',
                  key: 'name',
                },
                {
                  title: 'URL',
                  dataIndex: 'url',
                  key: 'url',
                  render: (text) => <a href={text} target="_blank" rel="noopener noreferrer">{text}</a>,
                },
                {
                  title: '类别',
                  dataIndex: 'category',
                  key: 'category',
                  render: (_, record) => {
                    const category = categories.find(c => c.id === record.category_id);
                    return category ? category.name : '-';
                  },
                },
                {
                  title: '操作',
                  key: 'actions',
                  render: (_: any, record: NewsSource) => (
                    <Space>
                      <Button 
                        icon={<EditOutlined />} 
                        onClick={() => showEditSourceModal(record)}
                        size="small"
                      >
                        编辑
                      </Button>
                      <Popconfirm
                        title="确定要删除此来源吗？"
                        onConfirm={() => handleDeleteSource(record.id)}
                        okText="是"
                        cancelText="否"
                      >
                        <Button 
                          danger 
                          icon={<DeleteOutlined />}
                          size="small"
                        >
                          删除
                        </Button>
                      </Popconfirm>
                    </Space>
                  ),
                },
              ]} 
              rowKey="id"
              loading={loading}
            />
          </TabPane>
        </Tabs>
      </div>
      
      {/* API Key Modal */}
      <Modal
        title={editingApiKey ? '编辑API密钥' : '添加API密钥'}
        open={isApiKeyModalVisible}
        onOk={handleApiKeySave}
        onCancel={() => setIsApiKeyModalVisible(false)}
        okText={editingApiKey ? '更新' : '创建'}
        cancelText="取消"
      >
        <Form 
          form={apiKeyForm} 
          layout="vertical"
          initialValues={{ context: 16000, max_output_tokens: 4000 }}
        >
          <Form.Item
            name="model"
            label="模型名称"
            rules={[{ required: true, message: '请输入模型名称' }]}
          >
            <Input placeholder="例如: deepseek-chat" />
          </Form.Item>
          
          <Form.Item
            name="base_url"
            label="API基础URL"
            rules={[{ required: true, message: '请输入API基础URL' }]}
          >
            <Input placeholder="例如: https://api.deepseek.com" />
          </Form.Item>
          
          <Form.Item
            name="api_key"
            label="API密钥"
            rules={[{ required: true, message: '请输入API密钥' }]}
          >
            <Input.Password placeholder="输入API密钥" />
          </Form.Item>
          
          <Form.Item
            name="context"
            label="上下文长度"
            rules={[
              { required: true, message: '请输入上下文长度' },
              { type: 'number', min: 1, message: '上下文长度必须为正整数' }
            ]}
          >
            <InputNumber style={{ width: '100%' }} placeholder="例如: 16000" />
          </Form.Item>
          
          <Form.Item
            name="max_output_tokens"
            label="最大输出Token"
            rules={[
              { required: true, message: '请输入最大输出Token' },
              { type: 'number', min: 1, message: '最大输出Token必须为正整数' },
              ({ getFieldValue }) => ({
                validator(_, value) {
                  if (!value || getFieldValue('context') > value) {
                    return Promise.resolve();
                  }
                  return Promise.reject(new Error('上下文长度必须大于最大输出Token'));
                },
              }),
            ]}
          >
            <InputNumber style={{ width: '100%' }} placeholder="例如: 4000" />
          </Form.Item>
          
          <Form.Item
            name="description"
            label="说明"
          >
            <Input.TextArea placeholder="可选说明" />
          </Form.Item>
        </Form>
      </Modal>
      
      {/* Source Modal */}
      <Modal
        title={editingSourceId ? '编辑来源' : '添加来源'}
        open={isSourceModalVisible}
        onOk={handleSourceSave}
        onCancel={() => setIsSourceModalVisible(false)}
        okText={editingSourceId ? '更新' : '创建'}
        cancelText="取消"
        width={600}
      >
        <Form form={sourceForm} layout="vertical">
          <Form.Item
            name="name"
            label="来源名称"
            rules={[{ required: true, message: '请输入来源名称' }]}
          >
            <Input />
          </Form.Item>
          
          <Form.Item
            name="url"
            label="URL"
            rules={[
              { required: true, message: '请输入URL' },
              { type: 'url', message: '请输入有效的URL' }
            ]}
          >
            <Input />
          </Form.Item>
          
          <Form.Item
            name="category_id"
            label={
              <Space>
                <span>类别</span>
                <Button 
                  type="link" 
                  icon={<PlusOutlined />} 
                  onClick={handleAddCategoryClick}
                  size="small"
                >
                  添加类别
                </Button>
              </Space>
            }
            rules={[{ required: true, message: '请选择类别' }]}
          >
            <Select>
              {categories.map(category => (
                <Option key={category.id} value={category.id}>{category.name}</Option>
              ))}
            </Select>
          </Form.Item>
          
          <div style={{ marginBottom: 16 }}>
            <div style={{ marginBottom: 8 }}>已有类别:</div>
            <div>
              {categories.map(category => (
                <Tag 
                  key={category.id} 
                  closable 
                  onClose={(e) => {
                    e.preventDefault();
                    handleDeleteCategoryTag(category.id);
                  }}
                  style={{ marginBottom: 8 }}
                >
                  {category.name}
                </Tag>
              ))}
            </div>
          </div>
        </Form>
      </Modal>
      
      {/* Add Category Modal */}
      <Modal
        title="添加新类别"
        open={isAddCategoryModalVisible}
        onOk={handleCreateCategory}
        onCancel={() => setIsAddCategoryModalVisible(false)}
        okText="创建"
        cancelText="取消"
      >
        <Form layout="vertical">
          <Form.Item
            label="类别名称"
            rules={[{ required: true, message: '请输入类别名称' }]}
          >
            <Input 
              value={newCategoryName} 
              onChange={(e) => setNewCategoryName(e.target.value)} 
              placeholder="输入新类别名称"
            />
          </Form.Item>
        </Form>
      </Modal>
    </MainLayout>
  );
};

export default Settings;

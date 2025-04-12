import React, { useEffect, useState } from 'react';
import {
    Box,
    Typography,
    Paper,
    Tabs,
    Tab,
    Table,
    TableBody,
    TableCell,
    TableContainer,
    TableHead,
    TableRow,
    Button,
    IconButton,
    TextField,
    Dialog,
    DialogTitle,
    DialogContent,
    DialogActions,
    CircularProgress,
    Snackbar,
    Alert
} from '@mui/material';
import AddIcon from '@mui/icons-material/Add';
import EditIcon from '@mui/icons-material/Edit';
import DeleteIcon from '@mui/icons-material/Delete';
import { useSettingsStore } from '../store/settingsStore';
import { ApiKeyCreate, SystemConfigCreate } from '../types/settings';

interface TabPanelProps {
    children?: React.ReactNode;
    index: number;
    value: number;
}

const TabPanel: React.FC<TabPanelProps> = (props) => {
    const { children, value, index, ...other } = props;

    return (
        <div
            role="tabpanel"
            hidden={value !== index}
            id={`settings-tabpanel-${index}`}
            aria-labelledby={`settings-tab-${index}`}
            {...other}
        >
            {value === index && (
                <Box sx={{ p: 3 }}>
                    {children}
                </Box>
            )}
        </div>
    );
};

const SettingsView: React.FC = () => {
    // 状态管理
    const {
        apiKeys,
        systemConfigs,
        isLoading,
        error,
        fetchApiKeys,
        createApiKey,
        updateApiKey,
        deleteApiKey,
        fetchSystemConfigs,
        createSystemConfig,
        updateSystemConfig,
        deleteSystemConfig
    } = useSettingsStore();

    // 本地状态
    const [tabValue, setTabValue] = useState(0);
    const [openApiKeyDialog, setOpenApiKeyDialog] = useState(false);
    const [openConfigDialog, setOpenConfigDialog] = useState(false);
    const [editingApiKey, setEditingApiKey] = useState<{ service: string, key: string } | null>(null);
    const [editingConfig, setEditingConfig] = useState<{ key: string, value: any } | null>(null);
    const [snackbarOpen, setSnackbarOpen] = useState(false);
    const [snackbarMessage, setSnackbarMessage] = useState('');
    const [snackbarSeverity, setSnackbarSeverity] = useState<'success' | 'error'>('success');

    // 获取数据
    useEffect(() => {
        fetchApiKeys();
        fetchSystemConfigs();
    }, [fetchApiKeys, fetchSystemConfigs]);

    // Tab切换
    const handleTabChange = (event: React.SyntheticEvent, newValue: number) => {
        setTabValue(newValue);
    };

    // API Key对话框
    const handleOpenApiKeyDialog = (apiKey?: { service: string, key: string }) => {
        if (apiKey) {
            setEditingApiKey(apiKey);
        } else {
            setEditingApiKey({ service: '', key: '' });
        }
        setOpenApiKeyDialog(true);
    };

    const handleCloseApiKeyDialog = () => {
        setOpenApiKeyDialog(false);
        setEditingApiKey(null);
    };

    const handleSaveApiKey = async () => {
        if (!editingApiKey) return;

        try {
            if (editingApiKey.service.trim() === '' || editingApiKey.key.trim() === '') {
                setSnackbarMessage('服务名称和密钥不能为空');
                setSnackbarSeverity('error');
                setSnackbarOpen(true);
                return;
            }

            const existingKey = apiKeys.find(k => k.service === editingApiKey.service);

            if (existingKey) {
                await updateApiKey(editingApiKey.service, editingApiKey.key);
                setSnackbarMessage(`API密钥 "${editingApiKey.service}" 已更新`);
            } else {
                await createApiKey(editingApiKey as ApiKeyCreate);
                setSnackbarMessage(`API密钥 "${editingApiKey.service}" 已创建`);
            }

            setSnackbarSeverity('success');
            setSnackbarOpen(true);
            handleCloseApiKeyDialog();
        } catch (err) {
            setSnackbarMessage(`操作失败: ${err instanceof Error ? err.message : '未知错误'}`);
            setSnackbarSeverity('error');
            setSnackbarOpen(true);
        }
    };

    const handleDeleteApiKey = async (service: string) => {
        try {
            await deleteApiKey(service);
            setSnackbarMessage(`API密钥 "${service}" 已删除`);
            setSnackbarSeverity('success');
            setSnackbarOpen(true);
        } catch (err) {
            setSnackbarMessage(`删除失败: ${err instanceof Error ? err.message : '未知错误'}`);
            setSnackbarSeverity('error');
            setSnackbarOpen(true);
        }
    };

    // 系统配置对话框
    const handleOpenConfigDialog = (config?: { key: string, value: any }) => {
        if (config) {
            setEditingConfig(config);
        } else {
            setEditingConfig({ key: '', value: '' });
        }
        setOpenConfigDialog(true);
    };

    const handleCloseConfigDialog = () => {
        setOpenConfigDialog(false);
        setEditingConfig(null);
    };

    const handleSaveConfig = async () => {
        if (!editingConfig) return;

        try {
            if (editingConfig.key.trim() === '') {
                setSnackbarMessage('配置键不能为空');
                setSnackbarSeverity('error');
                setSnackbarOpen(true);
                return;
            }

            const existingConfig = systemConfigs.find(c => c.key === editingConfig.key);

            if (existingConfig) {
                await updateSystemConfig(editingConfig.key, editingConfig.value);
                setSnackbarMessage(`系统配置 "${editingConfig.key}" 已更新`);
            } else {
                await createSystemConfig(editingConfig as SystemConfigCreate);
                setSnackbarMessage(`系统配置 "${editingConfig.key}" 已创建`);
            }

            setSnackbarSeverity('success');
            setSnackbarOpen(true);
            handleCloseConfigDialog();
        } catch (err) {
            setSnackbarMessage(`操作失败: ${err instanceof Error ? err.message : '未知错误'}`);
            setSnackbarSeverity('error');
            setSnackbarOpen(true);
        }
    };

    const handleDeleteConfig = async (key: string) => {
        try {
            await deleteSystemConfig(key);
            setSnackbarMessage(`系统配置 "${key}" 已删除`);
            setSnackbarSeverity('success');
            setSnackbarOpen(true);
        } catch (err) {
            setSnackbarMessage(`删除失败: ${err instanceof Error ? err.message : '未知错误'}`);
            setSnackbarSeverity('error');
            setSnackbarOpen(true);
        }
    };

    // 关闭通知
    const handleCloseSnackbar = () => {
        setSnackbarOpen(false);
    };

    return (
        <Box sx={{ p: 3, height: '100%' }}>
            <Typography variant="h4" gutterBottom>系统设置</Typography>

            <Paper sx={{ width: '100%' }}>
                <Tabs
                    value={tabValue}
                    onChange={handleTabChange}
                    aria-label="设置选项卡"
                >
                    <Tab label="API密钥" />
                    <Tab label="系统配置" />
                </Tabs>

                {/* API密钥面板 */}
                <TabPanel value={tabValue} index={0}>
                    <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
                        <Typography variant="h6">API密钥管理</Typography>
                        <Button
                            variant="contained"
                            startIcon={<AddIcon />}
                            onClick={() => handleOpenApiKeyDialog()}
                        >
                            添加密钥
                        </Button>
                    </Box>

                    {isLoading ? (
                        <Box sx={{ display: 'flex', justifyContent: 'center', p: 4 }}>
                            <CircularProgress />
                        </Box>
                    ) : (
                        <TableContainer>
                            <Table>
                                <TableHead>
                                    <TableRow>
                                        <TableCell>服务</TableCell>
                                        <TableCell>密钥</TableCell>
                                        <TableCell>更新时间</TableCell>
                                        <TableCell align="right">操作</TableCell>
                                    </TableRow>
                                </TableHead>
                                <TableBody>
                                    {apiKeys.length > 0 ? (
                                        apiKeys.map((key) => (
                                            <TableRow key={key.id}>
                                                <TableCell>{key.service}</TableCell>
                                                <TableCell>
                                                    {key.key.substring(0, 8)}...
                                                </TableCell>
                                                <TableCell>
                                                    {new Date(key.updated_at).toLocaleString()}
                                                </TableCell>
                                                <TableCell align="right">
                                                    <IconButton
                                                        size="small"
                                                        onClick={() => handleOpenApiKeyDialog({ service: key.service, key: key.key })}
                                                    >
                                                        <EditIcon fontSize="small" />
                                                    </IconButton>
                                                    <IconButton
                                                        size="small"
                                                        color="error"
                                                        onClick={() => handleDeleteApiKey(key.service)}
                                                    >
                                                        <DeleteIcon fontSize="small" />
                                                    </IconButton>
                                                </TableCell>
                                            </TableRow>
                                        ))
                                    ) : (
                                        <TableRow>
                                            <TableCell colSpan={4} align="center">
                                                <Typography variant="body2" color="text.secondary">
                                                    暂无API密钥
                                                </Typography>
                                            </TableCell>
                                        </TableRow>
                                    )}
                                </TableBody>
                            </Table>
                        </TableContainer>
                    )}
                </TabPanel>

                {/* 系统配置面板 */}
                <TabPanel value={tabValue} index={1}>
                    <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
                        <Typography variant="h6">系统配置</Typography>
                        <Button
                            variant="contained"
                            startIcon={<AddIcon />}
                            onClick={() => handleOpenConfigDialog()}
                        >
                            添加配置
                        </Button>
                    </Box>

                    {isLoading ? (
                        <Box sx={{ display: 'flex', justifyContent: 'center', p: 4 }}>
                            <CircularProgress />
                        </Box>
                    ) : (
                        <TableContainer>
                            <Table>
                                <TableHead>
                                    <TableRow>
                                        <TableCell>配置键</TableCell>
                                        <TableCell>配置值</TableCell>
                                        <TableCell>更新时间</TableCell>
                                        <TableCell align="right">操作</TableCell>
                                    </TableRow>
                                </TableHead>
                                <TableBody>
                                    {systemConfigs.length > 0 ? (
                                        systemConfigs.map((config) => (
                                            <TableRow key={config.id}>
                                                <TableCell>{config.key}</TableCell>
                                                <TableCell>
                                                    {typeof config.value === 'object'
                                                        ? JSON.stringify(config.value).substring(0, 30) + (JSON.stringify(config.value).length > 30 ? '...' : '')
                                                        : String(config.value)}
                                                </TableCell>
                                                <TableCell>
                                                    {new Date(config.updated_at).toLocaleString()}
                                                </TableCell>
                                                <TableCell align="right">
                                                    <IconButton
                                                        size="small"
                                                        onClick={() => handleOpenConfigDialog({ key: config.key, value: config.value })}
                                                    >
                                                        <EditIcon fontSize="small" />
                                                    </IconButton>
                                                    <IconButton
                                                        size="small"
                                                        color="error"
                                                        onClick={() => handleDeleteConfig(config.key)}
                                                    >
                                                        <DeleteIcon fontSize="small" />
                                                    </IconButton>
                                                </TableCell>
                                            </TableRow>
                                        ))
                                    ) : (
                                        <TableRow>
                                            <TableCell colSpan={4} align="center">
                                                <Typography variant="body2" color="text.secondary">
                                                    暂无系统配置
                                                </Typography>
                                            </TableCell>
                                        </TableRow>
                                    )}
                                </TableBody>
                            </Table>
                        </TableContainer>
                    )}
                </TabPanel>
            </Paper>

            {/* API密钥对话框 */}
            <Dialog open={openApiKeyDialog} onClose={handleCloseApiKeyDialog}>
                <DialogTitle>
                    {editingApiKey && apiKeys.some(k => k.service === editingApiKey.service)
                        ? `编辑API密钥: ${editingApiKey.service}`
                        : '添加API密钥'}
                </DialogTitle>
                <DialogContent>
                    <TextField
                        autoFocus
                        margin="dense"
                        label="服务名称"
                        fullWidth
                        variant="outlined"
                        value={editingApiKey?.service || ''}
                        onChange={(e) => setEditingApiKey({ ...editingApiKey!, service: e.target.value })}
                        disabled={editingApiKey && apiKeys.some(k => k.service === editingApiKey.service)}
                        sx={{ mb: 2 }}
                    />
                    <TextField
                        margin="dense"
                        label="API密钥"
                        fullWidth
                        variant="outlined"
                        value={editingApiKey?.key || ''}
                        onChange={(e) => setEditingApiKey({ ...editingApiKey!, key: e.target.value })}
                    />
                </DialogContent>
                <DialogActions>
                    <Button onClick={handleCloseApiKeyDialog}>取消</Button>
                    <Button onClick={handleSaveApiKey} variant="contained">保存</Button>
                </DialogActions>
            </Dialog>

            {/* 系统配置对话框 */}
            <Dialog open={openConfigDialog} onClose={handleCloseConfigDialog}>
                <DialogTitle>
                    {editingConfig && systemConfigs.some(c => c.key === editingConfig.key)
                        ? `编辑系统配置: ${editingConfig.key}`
                        : '添加系统配置'}
                </DialogTitle>
                <DialogContent>
                    <TextField
                        autoFocus
                        margin="dense"
                        label="配置键"
                        fullWidth
                        variant="outlined"
                        value={editingConfig?.key || ''}
                        onChange={(e) => setEditingConfig({ ...editingConfig!, key: e.target.value })}
                        disabled={editingConfig && systemConfigs.some(c => c.key === editingConfig.key)}
                        sx={{ mb: 2 }}
                    />
                    <TextField
                        margin="dense"
                        label="配置值"
                        fullWidth
                        multiline
                        rows={4}
                        variant="outlined"
                        value={editingConfig?.value || ''}
                        onChange={(e) => setEditingConfig({ ...editingConfig!, value: e.target.value })}
                    />
                </DialogContent>
                <DialogActions>
                    <Button onClick={handleCloseConfigDialog}>取消</Button>
                    <Button onClick={handleSaveConfig} variant="contained">保存</Button>
                </DialogActions>
            </Dialog>

            {/* 通知 */}
            <Snackbar
                open={snackbarOpen}
                autoHideDuration={6000}
                onClose={handleCloseSnackbar}
                anchorOrigin={{ vertical: 'bottom', horizontal: 'right' }}
            >
                <Alert
                    onClose={handleCloseSnackbar}
                    severity={snackbarSeverity}
                    sx={{ width: '100%' }}
                >
                    {snackbarMessage}
                </Alert>
            </Snackbar>
        </Box>
    );
};

export default SettingsView; 
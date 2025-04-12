import React, { useEffect, useState } from 'react';
import {
    Box,
    Typography,
    Paper,
    Button,
    TextField,
    FormControl,
    InputLabel,
    Select,
    MenuItem,
    Card,
    CardContent,
    CardActions,
    Grid,
    IconButton,
    SelectChangeEvent,
    CircularProgress
} from '@mui/material';
import { DataGrid, GridColDef } from '@mui/x-data-grid';
import RefreshIcon from '@mui/icons-material/Refresh';
import SearchIcon from '@mui/icons-material/Search';
import { useNewsStore } from '../store/newsStore';
import WorkspaceProgressModal from '../components/WorkspaceProgressModal';
import { NewsWebSocketClient } from '../services/websocket';
import { useWebSocket } from '../hooks/useWebSocket';
import { NewsWebSocketMessage } from '../types/news';

const NewsView: React.FC = () => {
    // 状态管理
    const {
        items,
        isLoading,
        error,
        selectedItem,
        categories,
        sources,
        selectedCategory,
        selectedSource,
        searchQuery,
        isProgressModalOpen,
        progressData,
        analysisChunks,
        fetchNewsItems,
        fetchCategories,
        fetchSources,
        selectItem,
        setSelectedCategory,
        setSelectedSource,
        setSearchQuery,
        openProgressModal,
        closeProgressModal,
        updateProgress,
        addAnalysisChunk,
        clearProgress
    } = useNewsStore();

    // WebSocket客户端
    const [wsClient] = useState(() => new NewsWebSocketClient());
    const { connected, messages, sendMessage } = useWebSocket<NewsWebSocketMessage>(wsClient);

    // 获取数据
    useEffect(() => {
        fetchNewsItems();
        fetchCategories();
        fetchSources();
    }, [fetchNewsItems, fetchCategories, fetchSources]);

    // 处理WebSocket消息
    useEffect(() => {
        if (messages.length > 0) {
            const lastMessage = messages[messages.length - 1];

            if (lastMessage.type === 'news_progress') {
                updateProgress(lastMessage.data);
            } else if (lastMessage.type === 'news_analysis_chunk') {
                addAnalysisChunk(lastMessage.data);
            }
        }
    }, [messages, updateProgress, addAnalysisChunk]);

    // 处理筛选变化
    const handleCategoryChange = (event: SelectChangeEvent) => {
        setSelectedCategory(event.target.value);
    };

    const handleSourceChange = (event: SelectChangeEvent) => {
        setSelectedSource(event.target.value);
    };

    const handleSearchChange = (event: React.ChangeEvent<HTMLInputElement>) => {
        setSearchQuery(event.target.value);
    };

    // 应用筛选器
    const handleApplyFilters = () => {
        fetchNewsItems(selectedCategory, selectedSource, searchQuery);
    };

    // 清除筛选器
    const handleClearFilters = () => {
        setSelectedCategory('');
        setSelectedSource('');
        setSearchQuery('');
        fetchNewsItems('', '', '');
    };

    // 获取新闻
    const handleFetchNews = () => {
        // 打开进度模态窗口
        openProgressModal();
        clearProgress();

        // 发送WebSocket请求
        if (connected) {
            sendMessage({
                command: 'fetch_news',
                data: {
                    category: selectedCategory || undefined,
                    source: selectedSource || undefined
                }
            });
        } else {
            console.error('WebSocket未连接');
        }
    };

    // 表格列定义
    const columns: GridColDef[] = [
        { field: 'title', headerName: '标题', flex: 1 },
        { field: 'source', headerName: '来源', width: 150 },
        { field: 'category', headerName: '分类', width: 150 },
        {
            field: 'published_at',
            headerName: '发布时间',
            width: 200,
            valueFormatter: (params) => {
                return new Date(params.value).toLocaleString();
            }
        }
    ];

    return (
        <Box sx={{ p: 3, height: '100%', display: 'flex', flexDirection: 'column' }}>
            <Typography variant="h4" gutterBottom>新闻资讯</Typography>

            {/* 筛选区 */}
            <Paper sx={{ p: 2, mb: 2 }}>
                <Grid container spacing={2} alignItems="center">
                    <Grid item xs={12} sm={6} md={3}>
                        <FormControl fullWidth size="small">
                            <InputLabel>分类</InputLabel>
                            <Select
                                value={selectedCategory}
                                label="分类"
                                onChange={handleCategoryChange}
                            >
                                <MenuItem value="">全部</MenuItem>
                                {categories.map((category) => (
                                    <MenuItem key={category} value={category}>{category}</MenuItem>
                                ))}
                            </Select>
                        </FormControl>
                    </Grid>

                    <Grid item xs={12} sm={6} md={3}>
                        <FormControl fullWidth size="small">
                            <InputLabel>来源</InputLabel>
                            <Select
                                value={selectedSource}
                                label="来源"
                                onChange={handleSourceChange}
                            >
                                <MenuItem value="">全部</MenuItem>
                                {sources.map((source) => (
                                    <MenuItem key={source} value={source}>{source}</MenuItem>
                                ))}
                            </Select>
                        </FormControl>
                    </Grid>

                    <Grid item xs={12} sm={6} md={3}>
                        <TextField
                            fullWidth
                            size="small"
                            label="搜索"
                            variant="outlined"
                            value={searchQuery}
                            onChange={handleSearchChange}
                            InputProps={{
                                endAdornment: (
                                    <IconButton
                                        size="small"
                                        onClick={handleApplyFilters}
                                        edge="end"
                                    >
                                        <SearchIcon />
                                    </IconButton>
                                ),
                            }}
                            onKeyPress={(e) => {
                                if (e.key === 'Enter') {
                                    handleApplyFilters();
                                }
                            }}
                        />
                    </Grid>

                    <Grid item xs={12} sm={6} md={3}>
                        <Box sx={{ display: 'flex', gap: 1 }}>
                            <Button
                                variant="outlined"
                                onClick={handleApplyFilters}
                                startIcon={<SearchIcon />}
                            >
                                筛选
                            </Button>

                            <Button
                                color="secondary"
                                onClick={handleClearFilters}
                            >
                                清除
                            </Button>

                            <Button
                                color="primary"
                                variant="contained"
                                onClick={handleFetchNews}
                                disabled={!connected}
                            >
                                获取资讯
                            </Button>
                        </Box>
                    </Grid>
                </Grid>
            </Paper>

            {/* 主内容区 */}
            <Box sx={{ display: 'flex', flexGrow: 1, gap: 2, height: 'calc(100% - 180px)' }}>
                {/* 新闻列表 */}
                <Box sx={{ flexGrow: 1, height: '100%' }}>
                    <DataGrid
                        rows={items}
                        columns={columns}
                        loading={isLoading}
                        initialState={{
                            pagination: {
                                paginationModel: { page: 0, pageSize: 10 },
                            },
                        }}
                        pageSizeOptions={[5, 10, 20]}
                        onRowClick={(params) => selectItem(params.row)}
                        autoHeight={false}
                        sx={{ height: '100%' }}
                        getRowClassName={(params) =>
                            params.id === selectedItem?.id ? 'selected-row' : ''
                        }
                    />
                </Box>

                {/* 预览区 */}
                <Card sx={{ width: '40%', overflow: 'auto', display: { xs: 'none', md: 'flex' }, flexDirection: 'column' }}>
                    {selectedItem ? (
                        <>
                            <CardContent sx={{ flexGrow: 1, overflow: 'auto' }}>
                                <Typography variant="h6">{selectedItem.title}</Typography>
                                <Typography variant="caption" color="text.secondary" display="block" gutterBottom>
                                    {new Date(selectedItem.published_at).toLocaleString()} · {selectedItem.source} · {selectedItem.category}
                                </Typography>
                                <Typography variant="subtitle1" sx={{ mt: 2 }}>摘要</Typography>
                                <Typography variant="body2" paragraph>
                                    {selectedItem.summary}
                                </Typography>
                                {selectedItem.analysis && (
                                    <>
                                        <Typography variant="subtitle1">分析</Typography>
                                        <Box sx={{ mt: 1, p: 1, bgcolor: '#f5f5f5', borderRadius: 1 }}>
                                            <Typography variant="body2">
                                                {selectedItem.analysis}
                                            </Typography>
                                        </Box>
                                    </>
                                )}
                            </CardContent>
                            <CardActions>
                                <Button
                                    size="small"
                                    href={selectedItem.url}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                >
                                    查看原文
                                </Button>
                            </CardActions>
                        </>
                    ) : (
                        <CardContent sx={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%' }}>
                            <Typography variant="body2" color="text.secondary">
                                选择一条新闻查看详情
                            </Typography>
                        </CardContent>
                    )}
                </Card>
            </Box>

            {/* 进度模态窗口 */}
            <WorkspaceProgressModal
                open={isProgressModalOpen}
                onClose={closeProgressModal}
                title="获取资讯进度"
                progress={progressData}
                markdownContent={analysisChunks}
            />

            {/* 错误提示 */}
            {error && (
                <Typography color="error" sx={{ mt: 2 }}>
                    {error}
                </Typography>
            )}
        </Box>
    );
};

export default NewsView; 
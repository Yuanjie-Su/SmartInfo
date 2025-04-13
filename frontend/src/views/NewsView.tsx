// src/views/NewsView.tsx
// This file contains the NewsView component, which displays a news feed with filtering and search capabilities.
// It uses Zustand for state management and a WebSocket client for real-time updates.

// 引入 React 相关的 hooks
import React, { useEffect, useState, useCallback } from 'react';
// 引入 MUI 组件库的常用组件
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import TextField from '@mui/material/TextField';
import FormControl from '@mui/material/FormControl';
import InputLabel from '@mui/material/InputLabel';
import Select, { SelectChangeEvent } from '@mui/material/Select';
import MenuItem from '@mui/material/MenuItem';
import CircularProgress from '@mui/material/CircularProgress';
import Alert from '@mui/material/Alert';
import { DataGrid, GridColDef, GridRowSelectionModel } from '@mui/x-data-grid';
// 引入自定义的 Zustand 状态管理 store
import { useNewsStore } from '../store/newsStore';
// 引入用于处理 WebSocket 的客户端
import { NewsWebSocketClient } from '../services/websocket';
// 引入获取新闻数据时显示进度的模态框组件
import FetchProgressModal from '../components/FetchProgressModal';
// MUI 的排版组件
import Typography from '@mui/material/Typography';
// lodash 中的防抖函数
import debounce from 'lodash/debounce';
// 引入类型定义
import {
    NewsItem,
    NewsCategory,
    NewsSource,
    NewsFetchProgressUpdate,
    NewsStreamChunkUpdate
} from '../types/news';

// 实例化一个 WebSocket 客户端对象
const newsWsClient = new NewsWebSocketClient();

// 定义主组件 NewsView，使用泛型指定为函数组件（React.FC）
const NewsView: React.FC = () => {
    // 从 Zustand store 中获取状态和操作
    const {
        items,
        isLoading,
        error,
        categories,
        sources,
        selectedCategory,
        selectedSource,
        searchQuery,
        fetchNewsItems,
        fetchCategories,
        fetchSources,
        setSelectedCategory,
        setSelectedSource,
        setSearchQuery,
        openProgressModal,
        closeProgressModal,
        isProgressModalOpen,
        fetchProgress: storeProgressData,
        fetchStreamChunks: storeAnalysisChunks,
        addProgressUpdate,
        addStreamChunk,
        clearFetchProgress,
        selectItem
    } = useNewsStore();

    // 定义本地搜索状态和更新函数
    const [localSearch, setLocalSearch] = useState(searchQuery); // localSearch：输入框绑定的值，立刻更新。

    // 使用 lodash 的防抖函数对搜索进行防抖处理
    const debouncedSearch = useCallback(
        debounce((query: string) => {
            setSearchQuery(query);
        }, 500),
        [setSearchQuery]
    );

    // 在组件挂载时获取新闻分类和来源
    useEffect(() => {
        fetchCategories();
        fetchSources();
    }, [fetchCategories, fetchSources]);

    // 在组件挂载时获取新闻数据
    useEffect(() => {
        fetchNewsItems(useNewsStore.getState().currentPage, useNewsStore.getState().pageSize);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [selectedCategory, selectedSource, searchQuery]);

    // 在组件挂载时连接 WebSocket
    useEffect(() => {
        const connectWs = async () => {
            if (!newsWsClient.isConnected()) {
                try {
                    await newsWsClient.connect();
                    console.log('News WebSocket connected');
                } catch (err) {
                    console.error('News WebSocket connection failed:', err);
                }
            }
        };
        connectWs();

        // 定义消息处理函数
        const removeMsgHandler = newsWsClient.onMessage((message) => {
            if (message.type === 'news_progress' && message.data) {
                addProgressUpdate(message.data as NewsFetchProgressUpdate);
                const progress = message.data as NewsFetchProgressUpdate;
                if (progress.status === 'completed' || progress.status === 'failed') {
                    fetchNewsItems();
                }
            } else if (message.type === 'stream_chunk' && message.data) {
                addStreamChunk((message.data as NewsStreamChunkUpdate).chunk);
            }
        });

        return () => {
            removeMsgHandler();
        };
    }, [fetchNewsItems, addProgressUpdate, addStreamChunk]);

    // 定义处理获取新闻点击事件的函数
    const handleFetchNewsClick = () => {
        clearFetchProgress();
        openProgressModal();
        newsWsClient.fetchNews({
            category_id: selectedCategory || undefined,
            source_id: selectedSource || undefined,
        });
    };

    // 定义处理分类选择变化的函数
    const handleCategoryChange = (event: SelectChangeEvent<number | string>) => {
        const value = event.target.value;
        setSelectedCategory(value === "" ? null : Number(value));
    };

    // 定义处理来源选择变化的函数
    const handleSourceChange = (event: SelectChangeEvent<number | string>) => {
        const value = event.target.value;
        setSelectedSource(value === "" ? null : Number(value));
    };

    // 定义处理搜索变化的函数
    const handleSearchChange = (event: React.ChangeEvent<HTMLInputElement>) => {
        setLocalSearch(event.target.value);
        debouncedSearch(event.target.value);
    };

    // 定义处理行选择变化的函数
    const handleRowSelection = (selectionModel: GridRowSelectionModel) => {
        const selectedId = selectionModel[0] as number | undefined;
        const selectedNewsItem = items.find(item => item.id === selectedId) || null;
        selectItem(selectedNewsItem);
    };

    // 定义表格的列定义
    const columns: GridColDef<NewsItem>[] = [
        { field: 'title', headerName: 'Title', flex: 3, minWidth: 250 },
        {
            field: 'category_name',
            headerName: 'Category',
            type: 'string',
            flex: 1,
            minWidth: 100,
            valueGetter: (_, row) => String(row.category_name ?? 'N/A')
        },
        {
            field: 'source_name',
            headerName: 'Source',
            type: 'string',
            flex: 1,
            minWidth: 100,
            valueGetter: (_, row) => String(row.source_name ?? 'N/A')
        },
        {
            field: 'date',
            headerName: 'Date',
            type: 'string',
            flex: 1,
            minWidth: 160,
            valueGetter: (value: string) => value ? new Date(value) : null
        },
    ];

    // 定义最后一条进度更新
    const lastProgressUpdate = storeProgressData.length > 0 ? storeProgressData[storeProgressData.length - 1] : null;

    // 返回组件的 JSX 结构
    return (
        <Box sx={{ p: 3, height: '100%', display: 'flex', flexDirection: 'column' }}>
            <Typography variant="h5" gutterBottom>News Feed</Typography>
            <Box sx={{ display: 'flex', gap: 2, mb: 2, flexWrap: 'wrap' }}>
                <Button variant="contained" onClick={handleFetchNewsClick} disabled={isProgressModalOpen}>
                    Fetch Latest News
                </Button>
                <FormControl sx={{ minWidth: 150 }}>
                    <InputLabel id="category-select-label">Category</InputLabel>
                    <Select<number | string>
                        labelId="category-select-label"
                        id="category-select"
                        value={selectedCategory ?? ""}
                        label="Category"
                        onChange={handleCategoryChange}
                    >
                        <MenuItem value=""><em>All Categories</em></MenuItem>
                        {categories.map((cat: NewsCategory) => (
                            <MenuItem key={cat.id} value={cat.id}>{cat.name}</MenuItem>
                        ))}
                    </Select>
                </FormControl>
                <FormControl sx={{ minWidth: 150 }}>
                    <InputLabel id="source-select-label">Source</InputLabel>
                    <Select<number | string>
                        labelId="source-select-label"
                        id="source-select"
                        value={selectedSource ?? ""}
                        label="Source"
                        onChange={handleSourceChange}
                    >
                        <MenuItem value=""><em>All Sources</em></MenuItem>
                        {sources.map((src: NewsSource) => (
                            <MenuItem key={src.id} value={src.id}>{src.name}</MenuItem>
                        ))}
                    </Select>
                </FormControl>
                <TextField
                    label="Search News"
                    variant="outlined"
                    value={localSearch}
                    onChange={handleSearchChange}
                    sx={{ flexGrow: 1, minWidth: 200 }}
                />
            </Box>

            {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

            <Box sx={{ flexGrow: 1, height: 'calc(100% - 150px)' }}>
                <DataGrid<NewsItem>
                    rows={items}
                    columns={columns}
                    initialState={{
                        pagination: { paginationModel: { pageSize: 25 } },
                    }}
                    pageSizeOptions={[10, 25, 50, 100]}
                    rowSelectionModel={useNewsStore.getState().selectedItem?.id ? [useNewsStore.getState().selectedItem!.id] : []}
                    onRowSelectionModelChange={handleRowSelection}
                    loading={isLoading && !isProgressModalOpen}
                    sx={{ '--DataGrid-overlayHeight': '300px' }}
                    getRowId={(row) => row.id}
                />
            </Box>

            <FetchProgressModal
                open={isProgressModalOpen}
                progressData={lastProgressUpdate}
                analysisText={storeAnalysisChunks.join('')}
                onClose={closeProgressModal}
            />
        </Box>
    );
};

export default NewsView;
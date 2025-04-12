import React, { useEffect, useState, useRef } from 'react';
import {
    Box,
    Typography,
    Paper,
    TextField,
    Button,
    List,
    ListItem,
    ListItemText,
    Divider,
    IconButton,
    CircularProgress
} from '@mui/material';
import SendIcon from '@mui/icons-material/Send';
import RefreshIcon from '@mui/icons-material/Refresh';
import ReactMarkdown from 'react-markdown';
import { useQAStore } from '../store/qaStore';
import { QAWebSocketClient } from '../services/websocket';
import { useWebSocket } from '../hooks/useWebSocket';
import { QAWebSocketMessage } from '../types/qa';

// 自定义消息组件
const MessageItem: React.FC<{
    content: string;
    isUser: boolean;
    isStreaming?: boolean;
}> = ({ content, isUser, isStreaming }) => {
    return (
        <Box
            sx={{
                display: 'flex',
                justifyContent: isUser ? 'flex-end' : 'flex-start',
                mb: 2,
            }}
        >
            <Paper
                elevation={1}
                sx={{
                    p: 2,
                    maxWidth: '80%',
                    backgroundColor: isUser ? '#e3f2fd' : '#f5f5f5',
                    borderRadius: 2,
                    position: 'relative'
                }}
            >
                {content ? (
                    <Box sx={{ minWidth: '100px' }}>
                        <ReactMarkdown>{content}</ReactMarkdown>
                    </Box>
                ) : (
                    <Box sx={{ display: 'flex', justifyContent: 'center', p: 1 }}>
                        <CircularProgress size={20} />
                    </Box>
                )}

                {isStreaming && (
                    <Box sx={{ position: 'absolute', right: 8, bottom: 8 }}>
                        <CircularProgress size={12} />
                    </Box>
                )}
            </Paper>
        </Box>
    );
};

const QAView: React.FC = () => {
    // 状态管理
    const {
        history,
        isLoading,
        error,
        messages,
        currentQuestion,
        isAnswering,
        currentAnswer,
        fetchHistory,
        setCurrentQuestion,
        addUserMessage,
        startAssistantResponse,
        updateAssistantResponse,
        completeAssistantResponse,
        clearMessages
    } = useQAStore();

    // WebSocket客户端
    const [wsClient] = useState(() => new QAWebSocketClient());
    const { connected, messages: wsMessages } = useWebSocket<QAWebSocketMessage>(wsClient);

    // 自动滚动到底部
    const messagesEndRef = useRef<HTMLDivElement>(null);

    const scrollToBottom = () => {
        messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    };

    // 获取历史记录
    useEffect(() => {
        fetchHistory();
    }, [fetchHistory]);

    // 处理WebSocket消息
    useEffect(() => {
        if (wsMessages.length > 0) {
            const lastMessage = wsMessages[wsMessages.length - 1];

            if (lastMessage.type === 'qa_stream' && lastMessage.data.partial_answer) {
                updateAssistantResponse(lastMessage.data.partial_answer);
            } else if (lastMessage.type === 'qa_complete') {
                completeAssistantResponse();
            }
        }
    }, [wsMessages, updateAssistantResponse, completeAssistantResponse]);

    // 自动滚动到底部
    useEffect(() => {
        scrollToBottom();
    }, [messages, currentAnswer]);

    // 处理问题提交
    const handleSubmit = () => {
        if (!currentQuestion.trim() || !connected || isAnswering) return;

        // 添加用户消息
        addUserMessage(currentQuestion);

        // 开始回答
        startAssistantResponse();

        // 发送WebSocket请求
        wsClient.askQuestion({ question: currentQuestion });
    };

    return (
        <Box sx={{ p: 3, height: '100%', display: 'flex' }}>
            {/* 主聊天区域 */}
            <Box sx={{ flexGrow: 1, display: 'flex', flexDirection: 'column', height: '100%' }}>
                <Typography variant="h4" gutterBottom>问答系统</Typography>

                {/* 消息显示区域 */}
                <Paper
                    sx={{
                        flexGrow: 1,
                        mb: 2,
                        p: 2,
                        overflow: 'auto',
                        display: 'flex',
                        flexDirection: 'column'
                    }}
                    elevation={1}
                >
                    {messages.length === 0 ? (
                        <Box sx={{
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            height: '100%',
                            color: 'text.secondary'
                        }}>
                            <Typography variant="body1">
                                开始提问，探索知识的海洋！
                            </Typography>
                        </Box>
                    ) : (
                        messages.map((message) => (
                            <MessageItem
                                key={message.id}
                                content={message.content}
                                isUser={message.type === 'user'}
                                isStreaming={message.isStreaming}
                            />
                        ))
                    )}
                    <div ref={messagesEndRef} />
                </Paper>

                {/* 输入区域 */}
                <Box sx={{ display: 'flex', gap: 1 }}>
                    <TextField
                        fullWidth
                        multiline
                        maxRows={4}
                        placeholder="输入您的问题..."
                        value={currentQuestion}
                        onChange={(e) => setCurrentQuestion(e.target.value)}
                        onKeyPress={(e) => {
                            if (e.key === 'Enter' && !e.shiftKey) {
                                e.preventDefault();
                                handleSubmit();
                            }
                        }}
                        disabled={!connected || isAnswering}
                    />
                    <Button
                        variant="contained"
                        color="primary"
                        endIcon={<SendIcon />}
                        onClick={handleSubmit}
                        disabled={!connected || !currentQuestion.trim() || isAnswering}
                        sx={{ height: 56 }}
                    >
                        发送
                    </Button>
                </Box>
            </Box>

            {/* 历史记录侧边栏 */}
            <Paper sx={{
                width: '300px',
                ml: 2,
                p: 2,
                display: { xs: 'none', md: 'block' },
                overflow: 'auto'
            }}>
                <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 1 }}>
                    <Typography variant="h6">历史记录</Typography>
                    <IconButton size="small" onClick={fetchHistory}>
                        <RefreshIcon fontSize="small" />
                    </IconButton>
                </Box>
                <Divider />

                {isLoading ? (
                    <Box sx={{ display: 'flex', justifyContent: 'center', p: 2 }}>
                        <CircularProgress size={24} />
                    </Box>
                ) : history.length > 0 ? (
                    <List dense>
                        {history.map((item) => (
                            <React.Fragment key={item.id}>
                                <ListItem
                                    button
                                    alignItems="flex-start"
                                    sx={{ py: 1 }}
                                >
                                    <ListItemText
                                        primary={item.question}
                                        secondary={
                                            <Typography
                                                variant="body2"
                                                color="text.secondary"
                                                sx={{
                                                    overflow: 'hidden',
                                                    textOverflow: 'ellipsis',
                                                    display: '-webkit-box',
                                                    WebkitLineClamp: 2,
                                                    WebkitBoxOrient: 'vertical',
                                                }}
                                            >
                                                {item.answer}
                                            </Typography>
                                        }
                                        primaryTypographyProps={{
                                            variant: 'subtitle2',
                                            noWrap: true
                                        }}
                                    />
                                </ListItem>
                                <Divider component="li" />
                            </React.Fragment>
                        ))}
                    </List>
                ) : (
                    <Box sx={{ p: 2, textAlign: 'center' }}>
                        <Typography variant="body2" color="text.secondary">
                            暂无历史记录
                        </Typography>
                    </Box>
                )}
            </Paper>

            {/* 错误提示 */}
            {error && (
                <Typography color="error" sx={{ mt: 2 }}>
                    {error}
                </Typography>
            )}
        </Box>
    );
};

export default QAView; 
// src/views/ChatView.tsx
import React, { useState, useEffect, useRef, useCallback } from 'react';
import Box from '@mui/material/Box';
import TextField from '@mui/material/TextField';
import IconButton from '@mui/material/IconButton';
import SendIcon from '@mui/icons-material/Send';
import Paper from '@mui/material/Paper';
import Typography from '@mui/material/Typography';
import CircularProgress from '@mui/material/CircularProgress';
import Alert from '@mui/material/Alert';
import ReactMarkdown from 'react-markdown';
import { useQAStore } from '../store/qaStore';
import { QAWebSocketClient } from '../services/websocket';

const qaWsClient = new QAWebSocketClient(); // Initialize client

const ChatView: React.FC = () => {
    const {
        messages,
        isLoading, // Use this for initial history loading if needed
        error,
        currentQuestion,
        isAnswering,
        setCurrentQuestion,
        addUserMessage,
        startAssistantResponse,
        updateAssistantResponse,
        completeAssistantResponse,
        fetchHistory, // If you want to load history
        resetCurrentAnswer,
        currentAnswer, // Get current answer for display during streaming
    } = useQAStore();

    const messagesEndRef = useRef<null | HTMLDivElement>(null);

    const scrollToBottom = () => {
        messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
    };

    useEffect(scrollToBottom, [messages, currentAnswer]); // Scroll when messages or currentAnswer changes

    // Load history (optional) and connect WebSocket
    useEffect(() => {
        // fetchHistory(); // Uncomment if you want to load history on mount

        const connectWs = async () => {
            if (!qaWsClient.isConnected()) {
                try {
                    await qaWsClient.connect();
                    console.log('QA WebSocket connected');
                } catch (err) {
                    console.error('QA WebSocket connection failed:', err);
                }
            }
        };
        connectWs();

        const removeMsgHandler = qaWsClient.onMessage((message) => {
            if (message.type === 'qa_stream') {
                if (message.data.partial_answer) {
                    updateAssistantResponse(message.data.partial_answer);
                }
                if (message.data.status === 'completed' || message.data.status === 'failed') {
                    completeAssistantResponse();
                    // Optionally show message.data.message if failed
                }
            }
            // Handle other message types like 'qa_complete' if your backend sends them
            else if (message.type === 'qa_complete') {
                completeAssistantResponse();
            }
        });

        return () => {
            removeMsgHandler();
            // Optional: disconnect or keep alive
            // qaWsClient.disconnect();
        };
    }, [updateAssistantResponse, completeAssistantResponse /*, fetchHistory */]);

    const handleSend = useCallback(() => {
        if (!currentQuestion.trim() || isAnswering || !qaWsClient.isConnected()) return;

        addUserMessage(currentQuestion);
        startAssistantResponse();
        resetCurrentAnswer(); // Reset just before asking

        qaWsClient.askQuestion({
            question: currentQuestion,
            // sources: [] // Add sources if applicable
        });

        setCurrentQuestion(''); // Clear input field after sending
    }, [currentQuestion, isAnswering, addUserMessage, startAssistantResponse, resetCurrentAnswer, setCurrentQuestion]);


    const handleInputChange = (event: React.ChangeEvent<HTMLInputElement>) => {
        setCurrentQuestion(event.target.value);
    };

    const handleKeyPress = (event: React.KeyboardEvent) => {
        if (event.key === 'Enter' && !event.shiftKey) {
            event.preventDefault(); // Prevent newline in textfield
            handleSend();
        }
    };

    return (
        <Box
            sx={{
                p: 2,
                height: '100%',
                display: 'flex',
                flexDirection: 'column',
                bgcolor: 'grey.100', // Light background for chat area
            }}
        >
            <Typography variant="h5" gutterBottom sx={{ px: 1 }}>Chat</Typography>

            {error && <Alert severity="error" sx={{ mb: 1, mx: 1 }}>{error}</Alert>}

            <Box
                sx={{
                    flexGrow: 1,
                    overflowY: 'auto',
                    mb: 2,
                    px: 1,
                    display: 'flex',
                    flexDirection: 'column',
                    gap: 2,
                }}
            >
                {messages.map((message) => (
                    <Paper
                        key={message.id}
                        elevation={1}
                        sx={{
                            p: 1.5,
                            maxWidth: '80%',
                            alignSelf: message.type === 'user' ? 'flex-end' : 'flex-start',
                            bgcolor: message.type === 'user' ? 'primary.light' : 'background.paper',
                            color: message.type === 'user' ? 'primary.contrastText' : 'text.primary',
                            wordBreak: 'break-word', // Ensure long words wrap
                        }}
                    >
                        {/* Render Markdown for assistant messages */}
                        {message.type === 'assistant' ? (
                            <ReactMarkdown>{message.content + (message.isStreaming ? '▍' : '')}</ReactMarkdown>
                        ) : (
                            <Typography variant="body1">{message.content}</Typography>
                        )}
                        <Typography variant="caption" display="block" sx={{ mt: 0.5, opacity: 0.7, textAlign: 'right' }}>
                            {message.timestamp.toLocaleTimeString()}
                        </Typography>
                    </Paper>
                ))}
                {/* Ref for scrolling */}
                <div ref={messagesEndRef} />
            </Box>

            <Box sx={{ display: 'flex', alignItems: 'center', p: 1, borderTop: '1px solid', borderColor: 'divider' }}>
                <TextField
                    fullWidth
                    variant="outlined"
                    placeholder="Type your message..."
                    value={currentQuestion}
                    onChange={handleInputChange}
                    onKeyPress={handleKeyPress}
                    disabled={isAnswering}
                    multiline
                    maxRows={4} // Allow some vertical expansion
                    sx={{ mr: 1, bgcolor: 'background.paper' }} // White background for input
                />
                <IconButton color="primary" onClick={handleSend} disabled={isAnswering || !currentQuestion.trim()}>
                    {isAnswering ? <CircularProgress size={24} /> : <SendIcon />}
                </IconButton>
            </Box>
        </Box>
    );
};

export default ChatView;
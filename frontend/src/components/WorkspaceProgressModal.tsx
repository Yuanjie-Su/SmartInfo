import React, { useEffect, useRef } from 'react';
import {
    Dialog,
    DialogTitle,
    DialogContent,
    DialogActions,
    Button,
    Typography,
    Box,
    LinearProgress,
    Paper,
    Divider
} from '@mui/material';
import ReactMarkdown from 'react-markdown';
import { NewsProgressUpdate } from '../types/news';

interface WorkspaceProgressModalProps {
    open: boolean;
    onClose: () => void;
    title: string;
    progress: NewsProgressUpdate | null;
    markdownContent: string[];
}

const WorkspaceProgressModal: React.FC<WorkspaceProgressModalProps> = ({
    open,
    onClose,
    title,
    progress,
    markdownContent
}) => {
    const contentRef = useRef<HTMLDivElement>(null);

    // 自动滚动到底部
    useEffect(() => {
        if (contentRef.current) {
            contentRef.current.scrollTop = contentRef.current.scrollHeight;
        }
    }, [markdownContent, progress]);

    // 计算进度百分比
    const progressPercentage = progress ?
        Math.round((progress.completed_tasks / progress.total_tasks) * 100) : 0;

    const isCompleted = progress?.status === 'completed';
    const isFailed = progress?.status === 'failed';

    return (
        <Dialog
            open={open}
            onClose={isCompleted || isFailed ? onClose : undefined}
            maxWidth="md"
            fullWidth
        >
            <DialogTitle>{title}</DialogTitle>
            <DialogContent>
                {progress && (
                    <Box sx={{ mb: 2 }}>
                        <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 1 }}>
                            <Typography variant="body2" color="text.secondary">
                                {progress.current_stage}
                            </Typography>
                            <Typography variant="body2" color="text.secondary">
                                {progressPercentage}% ({progress.completed_tasks}/{progress.total_tasks})
                            </Typography>
                        </Box>
                        <LinearProgress
                            variant="determinate"
                            value={progressPercentage}
                            color={isFailed ? 'error' : isCompleted ? 'success' : 'primary'}
                            sx={{ height: 8, borderRadius: 4 }}
                        />
                        <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
                            {progress.message}
                        </Typography>
                    </Box>
                )}

                <Divider sx={{ my: 2 }} />

                <Typography variant="subtitle1" gutterBottom>
                    分析结果:
                </Typography>

                <Paper
                    variant="outlined"
                    sx={{
                        p: 2,
                        height: 300,
                        overflow: 'auto',
                        backgroundColor: '#f5f5f5'
                    }}
                    ref={contentRef}
                >
                    {markdownContent.map((chunk, index) => (
                        <ReactMarkdown key={index}>{chunk}</ReactMarkdown>
                    ))}
                    {markdownContent.length === 0 && (
                        <Typography variant="body2" color="text.secondary" sx={{ fontStyle: 'italic' }}>
                            等待分析开始...
                        </Typography>
                    )}
                </Paper>
            </DialogContent>
            <DialogActions>
                <Button
                    onClick={onClose}
                    color={isCompleted ? 'primary' : 'inherit'}
                    variant={isCompleted ? 'contained' : 'text'}
                    disabled={!isCompleted && !isFailed}
                >
                    {isCompleted ? '完成' : isFailed ? '关闭' : '处理中...'}
                </Button>
            </DialogActions>
        </Dialog>
    );
};

export default WorkspaceProgressModal; 
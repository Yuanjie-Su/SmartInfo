// src/components/FetchProgressModal.tsx
import React from 'react';
import Modal from '@mui/material/Modal';
import Box from '@mui/material/Box';
import Typography from '@mui/material/Typography';
import CircularProgress from '@mui/material/CircularProgress';
import LinearProgress from '@mui/material/LinearProgress'; // Optional for progress bar

interface FetchProgressModalProps {
    open: boolean;
    onClose: () => void;
    progressData: {
        status: string;
        message: string;
        progress?: number; // Optional progress percentage (0-100)
        total?: number;
        current?: number;
    } | null;
    analysisText: string;
}

const style = {
    position: 'absolute' as 'absolute',
    top: '50%',
    left: '50%',
    transform: 'translate(-50%, -50%)',
    width: 400,
    bgcolor: 'background.paper',
    border: '2px solid #000',
    boxShadow: 24,
    p: 4,
};

const FetchProgressModal: React.FC<FetchProgressModalProps> = ({
    open,
    onClose,
    progressData,
    analysisText,
}) => {
    return (
        <Modal
            open={open}
            onClose={onClose} // Consider if user should be able to close it
            aria-labelledby="fetch-progress-modal-title"
            aria-describedby="fetch-progress-modal-description"
        >
            <Box sx={style}>
                <Typography id="fetch-progress-modal-title" variant="h6" component="h2">
                    Fetching News Data
                </Typography>
                {progressData ? (
                    <>
                        <Typography sx={{ mt: 2 }}>
                            Status: {progressData.status}
                        </Typography>
                        <Typography sx={{ mt: 1 }}>
                            {progressData.message}
                        </Typography>
                        {/* Optional: Show progress bar */}
                        {progressData.progress !== undefined && (
                            <LinearProgress variant="determinate" value={progressData.progress} sx={{ mt: 2 }} />
                        )}
                        {/* Optional: Show current/total */}
                        {progressData.current !== undefined && progressData.total !== undefined && (
                            <Typography sx={{ mt: 1 }}>
                                {progressData.current} / {progressData.total}
                            </Typography>
                        )}
                        {/* Display analysis text if available */}
                        {analysisText && (
                            <Box sx={{ maxHeight: 200, overflowY: 'auto', mt: 2, border: '1px solid grey', p: 1 }}>
                                <Typography variant="body2" component="pre" sx={{ whiteSpace: 'pre-wrap' }}>
                                    {analysisText}
                                </Typography>
                            </Box>
                        )}
                        {/* Indicate completion */}
                        {progressData.status === 'completed' && (
                            <Typography color="success.main" sx={{ mt: 2 }}>
                                Fetch completed successfully!
                            </Typography>
                        )}
                        {progressData.status === 'failed' && (
                            <Typography color="error.main" sx={{ mt: 2 }}>
                                Fetch failed. Check logs for details.
                            </Typography>
                        )}
                    </>
                ) : (
                    <CircularProgress sx={{ mt: 2 }} />
                )}
                {/* Maybe add a close button if onClose is implemented */}
                {/* <Button onClick={onClose} sx={{ mt: 2 }}>Close</Button> */}
            </Box>
        </Modal>
    );
};

export default FetchProgressModal;

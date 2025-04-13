// src/components/settings/ApiKeySettings.tsx
import React, { useState } from 'react';
import { useSettingsStore } from '../../store/settingsStore';
import Box from '@mui/material/Box';
import List from '@mui/material/List';
import ListItem from '@mui/material/ListItem';
import ListItemText from '@mui/material/ListItemText';
import IconButton from '@mui/material/IconButton';
import DeleteIcon from '@mui/icons-material/Delete';
import EditIcon from '@mui/icons-material/Edit';
import TextField from '@mui/material/TextField';
import Button from '@mui/material/Button';
import Typography from '@mui/material/Typography';
import CircularProgress from '@mui/material/CircularProgress';
import Dialog from '@mui/material/Dialog'; // For editing/adding
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';

const ApiKeySettings: React.FC = () => {
    const { apiKeys, isLoading, error, createApiKey, updateApiKey, deleteApiKey } = useSettingsStore();
    const [openDialog, setOpenDialog] = useState(false);
    const [isEditing, setIsEditing] = useState(false);
    const [currentService, setCurrentService] = useState('');
    const [currentKey, setCurrentKey] = useState('');

    const handleAddClick = () => {
        setIsEditing(false);
        setCurrentService('');
        setCurrentKey('');
        setOpenDialog(true);
    };

    const handleEditClick = (apiKey: typeof apiKeys[0]) => {
        setIsEditing(true);
        setCurrentService(apiKey.service);
        setCurrentKey(apiKey.key); // Show existing key for potential update
        setOpenDialog(true);
    };

    const handleDeleteClick = async (service: string) => {
        if (window.confirm(`Are you sure you want to delete the API key for ${service}?`)) {
            await deleteApiKey(service);
        }
    };

    const handleDialogClose = () => {
        setOpenDialog(false);
    };

    const handleDialogSave = async () => {
        if (!currentService.trim() || !currentKey.trim()) {
            alert('Service and Key cannot be empty.'); // Simple validation
            return;
        }
        try {
            if (isEditing) {
                await updateApiKey(currentService, currentKey);
            } else {
                await createApiKey({ service: currentService, key: currentKey });
            }
            handleDialogClose();
        } catch (err) {
            console.error("Failed to save API key:", err);
            alert(`Error: ${err instanceof Error ? err.message : 'Unknown error'}`);
        }
    };


    return (
        <Box>
            <Typography variant="h6" gutterBottom>Manage API Keys</Typography>
            {isLoading && <CircularProgress size={20} />}
            {error && <Typography color="error">{error}</Typography>}
            <Button variant="contained" onClick={handleAddClick} sx={{ mb: 2 }}>
                Add API Key
            </Button>
            <List>
                {apiKeys.map((apiKey) => (
                    <ListItem
                        key={apiKey.service}
                        secondaryAction={
                            <>
                                {/* <IconButton edge="end" aria-label="edit" onClick={() => handleEditClick(apiKey)}>
                                    <EditIcon />
                                </IconButton> */}
                                <IconButton edge="end" aria-label="delete" onClick={() => handleDeleteClick(apiKey.service)}>
                                    <DeleteIcon />
                                </IconButton>
                            </>
                        }
                    >
                        <ListItemText
                            primary={apiKey.service}
                            secondary={"Key: ********" + apiKey.key.slice(-4)} // Mask key
                        />
                    </ListItem>
                ))}
            </List>

            {/* Add/Edit Dialog */}
            <Dialog open={openDialog} onClose={handleDialogClose}>
                <DialogTitle>{isEditing ? 'Edit API Key' : 'Add API Key'}</DialogTitle>
                <DialogContent>
                    <TextField
                        autoFocus
                        margin="dense"
                        id="service"
                        label="Service Name"
                        type="text"
                        fullWidth
                        variant="standard"
                        value={currentService}
                        onChange={(e) => setCurrentService(e.target.value)}
                        disabled={isEditing} // Don't allow changing service name when editing
                    />
                    <TextField
                        margin="dense"
                        id="key"
                        label="API Key"
                        type="password" // Use password type to obscure
                        fullWidth
                        variant="standard"
                        value={currentKey}
                        onChange={(e) => setCurrentKey(e.target.value)}
                    />
                </DialogContent>
                <DialogActions>
                    <Button onClick={handleDialogClose}>Cancel</Button>
                    <Button onClick={handleDialogSave} disabled={isLoading}>
                        {isLoading ? <CircularProgress size={24} /> : 'Save'}
                    </Button>
                </DialogActions>
            </Dialog>
        </Box>
    );
};

export default ApiKeySettings;
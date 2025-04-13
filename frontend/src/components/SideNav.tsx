// src/components/SideNav.tsx
import React from 'react';
import { useNavigate } from 'react-router-dom';
import Box from '@mui/material/Box';
import List from '@mui/material/List';
import ListItem from '@mui/material/ListItem';
import ListItemButton from '@mui/material/ListItemButton';
import ListItemIcon from '@mui/material/ListItemIcon';
import ListItemText from '@mui/material/ListItemText';
import Divider from '@mui/material/Divider';
import NewspaperIcon from '@mui/icons-material/Newspaper';
import ChatIcon from '@mui/icons-material/Chat';
import SettingsIcon from '@mui/icons-material/Settings';
import { WebviewWindow } from '@tauri-apps/api/webviewWindow'; // Updated import

const drawerWidth = 240;

interface SideNavProps {
    onNavigate: (view: 'news' | 'chat') => void;
}

const SideNav: React.FC<SideNavProps> = ({ onNavigate }) => {
    const navigate = useNavigate(); // Use navigate for internal routing if needed

    const openSettingsWindow = () => {
        // Check if window already exists (optional, depends on desired behavior)
        const existingWindow = WebviewWindow.getByLabel('settings');
        if (existingWindow) {
            existingWindow.setFocus();
            return;
        }

        // Create and open the new window
        const webview = new WebviewWindow('settings', {
            url: '/settings', // Route defined in App.tsx for the settings page
            title: 'Settings',
            width: 800,
            height: 600,
            minWidth: 600,
            minHeight: 400,
        });

        webview.once('tauri://created', () => {
            console.log('Settings window created');
        });

        webview.once('tauri://error', (e) => {
            console.error('Failed to create settings window:', e);
        });
    };


    return (
        <Box
            sx={{
                width: drawerWidth,
                flexShrink: 0,
                '& .MuiDrawer-paper': {
                    width: drawerWidth,
                    boxSizing: 'border-box',
                },
                height: '100vh',
                display: 'flex',
                flexDirection: 'column',
                borderRight: '1px solid rgba(0, 0, 0, 0.12)', // Add visual separation
            }}
        >
            <List sx={{ flexGrow: 1 }}>
                <ListItem disablePadding>
                    <ListItemButton onClick={() => onNavigate('news')}>
                        <ListItemIcon>
                            <NewspaperIcon />
                        </ListItemIcon>
                        <ListItemText primary="News" />
                    </ListItemButton>
                </ListItem>
                <ListItem disablePadding>
                    <ListItemButton onClick={() => onNavigate('chat')}>
                        <ListItemIcon>
                            <ChatIcon />
                        </ListItemIcon>
                        <ListItemText primary="Chat" />
                    </ListItemButton>
                </ListItem>
            </List>
            <Divider />
            <List>
                <ListItem disablePadding>
                    <ListItemButton onClick={openSettingsWindow}>
                        <ListItemIcon>
                            <SettingsIcon />
                        </ListItemIcon>
                        <ListItemText primary="Settings" />
                    </ListItemButton>
                </ListItem>
            </List>
        </Box>
    );
};

export default SideNav;
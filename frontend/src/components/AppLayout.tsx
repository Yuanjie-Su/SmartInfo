// src/components/AppLayout.tsx (New File)
import React, { useState } from 'react';
import { Box, Drawer, List, ListItem, ListItemButton, ListItemIcon, ListItemText, CssBaseline, Toolbar, Divider } from '@mui/material';
import ArticleIcon from '@mui/icons-material/Article'; // Icon for News
import SettingsIcon from '@mui/icons-material/Settings'; // Icon for Settings
// Import your page components
import NewsPage from './NewsPage';
import SettingsPage from './SettingsPage'; // Assuming you create this

const drawerWidth = 240; // Adjust width as needed

function AppLayout() {
    const [selectedPage, setSelectedPage] = useState<'news' | 'settings'>('news');

    const renderPage = () => {
        switch (selectedPage) {
            case 'news':
                return <NewsPage />;
            case 'settings':
                return <SettingsPage />;
            default:
                return <NewsPage />; // Default to news page
        }
    };

    const drawerContent = (
        <Box sx={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
            <Toolbar /> {/* Adds space matching AppBar height if you had one */}
            <List sx={{ flexGrow: 1 }}> {/* List takes available space */}
                <ListItem disablePadding>
                    <ListItemButton
                        selected={selectedPage === 'news'}
                        onClick={() => setSelectedPage('news')}
                    >
                        <ListItemIcon>
                            <ArticleIcon />
                        </ListItemIcon>
                        <ListItemText primary="资讯" />
                    </ListItemButton>
                </ListItem>
                {/* Add other main navigation items here if needed */}
            </List>

            {/* Settings item at the bottom */}
            <Box>
                <Divider />
                <List>
                    <ListItem disablePadding>
                        <ListItemButton
                            selected={selectedPage === 'settings'}
                            onClick={() => setSelectedPage('settings')}
                        >
                            <ListItemIcon>
                                <SettingsIcon />
                            </ListItemIcon>
                            <ListItemText primary="设置" />
                        </ListItemButton>
                    </ListItem>
                </List>
            </Box>
        </Box>
    );


    return (
        <Box sx={{ display: 'flex' }}>
            <CssBaseline /> {/* Ensures consistent baseline styling */}
            <Drawer
                variant="permanent"
                sx={{
                    width: drawerWidth,
                    flexShrink: 0,
                    [`& .MuiDrawer-paper`]: { width: drawerWidth, boxSizing: 'border-box', borderRight: 'none' }, // Style the drawer paper
                    // Match the light grey background from the image
                    backgroundColor: '#f8f8f8', // Example light grey
                }}
                anchor="left"
            >
                {drawerContent}
            </Drawer>

            {/* Main Content Area */}
            <Box
                component="main"
                sx={{
                    flexGrow: 1, // Takes remaining space
                    bgcolor: 'background.default', // Uses theme background (likely white/dark grey)
                    p: 3, // Padding around the content
                    height: '100vh', // Full viewport height
                    overflow: 'auto', // Allow scrolling if content overflows
                }}
            >
                {/* Optional: Add Toolbar space if using an AppBar */}
                {/* <Toolbar />  */}
                {renderPage()} {/* Render the selected page component */}
            </Box>
        </Box>
    );
}

export default AppLayout;
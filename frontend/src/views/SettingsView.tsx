// src/views/SettingsView.tsx
import React, { useState, useEffect } from 'react';
import Box from '@mui/material/Box';
import Tabs from '@mui/material/Tabs';
import Tab from '@mui/material/Tab';
import Typography from '@mui/material/Typography';
import CircularProgress from '@mui/material/CircularProgress';
import Alert from '@mui/material/Alert';
import ApiKeySettings from '../components/settings/ApiKeySettings'; // Create this component
import NewsConfigSettings from '../components/settings/NewsConfigSettings'; // Create this component
import { useSettingsStore } from '../store/settingsStore';

interface TabPanelProps {
    children?: React.ReactNode;
    index: number;
    value: number;
}

function TabPanel(props: TabPanelProps) {
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
}

function a11yProps(index: number) {
    return {
        id: `settings-tab-${index}`,
        'aria-controls': `settings-tabpanel-${index}`,
    };
}

const SettingsView: React.FC = () => {
    const [tabValue, setTabValue] = useState(0);
    const { isLoading, error, fetchApiKeys, fetchSystemConfigs } = useSettingsStore();

    useEffect(() => {
        // Fetch initial settings data when the component mounts
        fetchApiKeys();
        fetchSystemConfigs(); // Assuming news categories/sources might be stored here
    }, [fetchApiKeys, fetchSystemConfigs]);

    const handleTabChange = (event: React.SyntheticEvent, newValue: number) => {
        setTabValue(newValue);
    };

    return (
        <Box sx={{ width: '100%', p: 2 }}>
            <Typography variant="h4" gutterBottom>Settings</Typography>
            {isLoading && <CircularProgress sx={{ display: 'block', margin: '20px auto' }} />}
            {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
            <Box sx={{ borderBottom: 1, borderColor: 'divider' }}>
                <Tabs value={tabValue} onChange={handleTabChange} aria-label="Settings tabs">
                    <Tab label="API Keys" {...a11yProps(0)} />
                    <Tab label="News Configuration" {...a11yProps(1)} />
                    {/* Add more tabs as needed */}
                </Tabs>
            </Box>
            <TabPanel value={tabValue} index={0}>
                <ApiKeySettings />
            </TabPanel>
            <TabPanel value={tabValue} index={1}>
                <NewsConfigSettings />
            </TabPanel>
            {/* Add more TabPanels as needed */}
        </Box>
    );
};

export default SettingsView;
// src/App.tsx
import React, { useState } from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import Box from '@mui/material/Box';
import CssBaseline from '@mui/material/CssBaseline'; // Optional: for baseline styles
import SideNav from './components/SideNav';
import NewsView from './views/NewsView';
import ChatView from './views/ChatView';
import SettingsView from './views/SettingsView'; // Import the settings view

function App() {
  // State to control the main content view, could also use router path
  const [currentView, setCurrentView] = useState<'news' | 'chat'>('news');

  const handleNavigation = (view: 'news' | 'chat') => {
    setCurrentView(view);
  };

  return (
    <>
      {/* Use Routes to handle different windows/views */}
      <Routes>
        {/* Main application window layout */}
        <Route
          path="/"
          element={
            <Box sx={{ display: 'flex', height: '100vh' }}>
              <CssBaseline /> {/* Apply baseline styles */}
              <SideNav onNavigate={handleNavigation} />
              <Box
                component="main"
                sx={{
                  flexGrow: 1,
                  // bgcolor: 'background.default', // Optional background color
                  overflow: 'auto', // Ensure content panel can scroll if needed
                  height: '100vh', // Make sure it takes full height
                }}
              >
                {/* Render content based on state */}
                {currentView === 'news' && <NewsView />}
                {currentView === 'chat' && <ChatView />}
              </Box>
            </Box>
          }
        />
        {/* Route for the settings page content (opened in a new window) */}
        <Route path="/settings" element={<SettingsView />} />

        {/* Optional: Redirect unknown paths to home */}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </>
  );
}

export default App;
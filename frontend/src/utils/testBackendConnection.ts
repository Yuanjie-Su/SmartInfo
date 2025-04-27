/**
 * Utility script to test all major backend connections
 * Run this with: npx ts-node src/utils/testBackendConnection.ts
 */
import axios from 'axios';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

async function testBackendConnections() {
  console.log('Testing backend connections...');
  console.log(`API URL: ${API_URL}`);
  
  try {
    // Test 1: API Root / Health Check
    console.log('\n--- Testing API Health ---');
    const healthCheck = await axios.get(`${API_URL}/health`);
    console.log('Health check:', healthCheck.status, healthCheck.data);
    
    // Test 2: News Endpoints
    console.log('\n--- Testing News Endpoints ---');
    const news = await axios.get(`${API_URL}/api/news`);
    console.log('News endpoint:', news.status, `Retrieved ${news.data.length} news items`);
    
    // Test 3: Categories
    console.log('\n--- Testing Categories Endpoint ---');
    const categories = await axios.get(`${API_URL}/api/news/categories`);
    console.log('Categories endpoint:', categories.status, `Retrieved ${categories.data.length} categories`);
    
    // Test 4: Sources
    console.log('\n--- Testing Sources Endpoint ---');
    const sources = await axios.get(`${API_URL}/api/news/sources`);
    console.log('Sources endpoint:', sources.status, `Retrieved ${sources.data.length} sources`);
    
    // Test 5: Chat History
    console.log('\n--- Testing Chat History Endpoint ---');
    const chatHistory = await axios.get(`${API_URL}/api/chat/history`);
    console.log('Chat history endpoint:', chatHistory.status, `Retrieved ${chatHistory.data.length} chat sessions`);
    
    // Test 6: Settings
    console.log('\n--- Testing Settings Endpoint ---');
    const settings = await axios.get(`${API_URL}/api/settings`);
    console.log('Settings endpoint:', settings.status, 'Settings retrieved successfully');
    
    console.log('\n✅ All backend tests completed successfully!');
  } catch (error) {
    console.error('\n❌ Backend connection test failed:');
    if (axios.isAxiosError(error)) {
      console.error(`Error: ${error.message}`);
      console.error(`Status: ${error.response?.status}`);
      console.error(`Data:`, error.response?.data);
    } else {
      console.error(error);
    }
    console.error('\nPlease make sure the backend server is running at:', API_URL);
  }
}

// Run the tests
testBackendConnections(); 
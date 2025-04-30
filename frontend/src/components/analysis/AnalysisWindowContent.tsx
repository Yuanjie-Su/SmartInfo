import React, { useState, useEffect } from 'react';
import { Typography, Spin, Alert, Space, Divider, Empty, Tooltip } from 'antd';
import { LinkOutlined } from '@ant-design/icons';
import { NewsItem } from '@/utils/types';
import * as newsService from '@/services/newsService';
import { handleApiError } from '@/utils/apiErrorHandler';

const { Title, Text, Paragraph } = Typography;

interface AnalysisWindowContentProps {
  newsItemId: number;
}

// Define a fixed height for the content area within the modal.
// Adjust this value based on your modal's design and desired appearance.
// You might calculate this based on viewport height if the modal is responsive.
const FIXED_CONTENT_HEIGHT = '65vh'; // Example: Use viewport height relative value
// const FIXED_CONTENT_HEIGHT = '550px'; // Example: Use fixed pixels

const AnalysisWindowContent: React.FC<AnalysisWindowContentProps> = ({ newsItemId }) => {
  const [newsItem, setNewsItem] = useState<NewsItem | null>(null);
  const [analysisContent, setAnalysisContent] = useState<string>('');
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [isStreaming, setIsStreaming] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchNewsAndAnalyze = async () => {
      setIsLoading(true);
      setError(null);
      setAnalysisContent('');

      try {
        const item = await newsService.getNewsById(newsItemId); // Excludes content by default now
        if (!item) {
          setError('News item not found.');
          setIsLoading(false);
          return;
        }
        setNewsItem(item);

        if (item.analysis) {
          setAnalysisContent(item.analysis);
          setIsLoading(false);
          setIsStreaming(false);
        } else {
          setIsStreaming(true);
          setIsLoading(true); // Keep loading spinner until first chunk or error

          try {
            const response = await newsService.streamAnalysis(newsItemId);
            if (!response.body) throw new Error("Streaming response body is empty.");

            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let receivedContent = '';
            let firstChunkReceived = false; // Flag to remove spinner on first data

            while (true) {
              const { done, value } = await reader.read();
              if (done) break;

              if (!firstChunkReceived) {
                setIsLoading(false); // Remove spinner once data starts arriving
                firstChunkReceived = true;
              }

              const decodedChunk = decoder.decode(value, { stream: true });
              receivedContent += decodedChunk;
              // Update state less aggressively if needed for extreme performance cases,
              // but usually direct update is fine with the fixed layout.
              setAnalysisContent(prev => prev + decodedChunk);
            }

            const finalChunk = decoder.decode();
            if (finalChunk) {
              setAnalysisContent(prev => prev + finalChunk);
            }

            if (!firstChunkReceived) { // Handle case where stream ends immediately with no data
                setIsLoading(false);
                setAnalysisContent('No analysis generated or content available.');
            }

          } catch (streamError) {
            console.error("Streaming analysis failed:", streamError);
            handleApiError(streamError, 'Failed to stream analysis');
            setError('Failed to stream analysis content.');
            setIsLoading(false); // Ensure loading stops on error
          } finally {
            setIsStreaming(false);
          }
        }
      } catch (fetchError) {
        console.error("Failed to fetch news item:", fetchError);
        handleApiError(fetchError, 'Failed to load news item');
        setError('Failed to load news item details.');
        setIsLoading(false);
        setIsStreaming(false);
      }
    };

    if (newsItemId) {
      fetchNewsAndAnalyze();
    }
  }, [newsItemId]);

  // --- Render Logic ---

  // Loading State (Initial fetch before content/analysis is known)
  if (isLoading && !newsItem) {
    return (
      <div style={{ height: FIXED_CONTENT_HEIGHT, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '20px' }}>
        <Spin size="large" tip="Loading news item..." />
      </div>
    );
  }

  // Error State
  if (error) {
    return (
      <div style={{ height: FIXED_CONTENT_HEIGHT, padding: '20px' }}>
        <Alert message="Error" description={error} type="error" showIcon />
      </div>
    );
  }

  // No News Item Found State (Should ideally not happen if ID is valid, but good practice)
  if (!newsItem) {
    return (
      <div style={{ height: FIXED_CONTENT_HEIGHT, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '20px' }}>
        <Empty description="News item not found." />
      </div>
    );
  }

  // Content Display State (Fixed Height Flex Layout)
  return (
    <div style={{
      height: FIXED_CONTENT_HEIGHT, // Apply the fixed height HERE
      display: 'flex',
      flexDirection: 'column',
      padding: '20px',
      overflow: 'hidden' // Prevent main container from scrolling
    }}>
      {/* --- Top Section (Static Height) --- */}
      <div style={{ flexShrink: 0 }}> {/* Prevent this part from shrinking */}
        <Title level={4} style={{ marginBottom: '8px', marginTop: 0 }}>{newsItem.title}</Title>
        {/* Generated by Copilot */}
        {/* Generated by Copilot */}
        <Space size={16} wrap style={{ marginBottom: '12px', fontSize: '12px' }}>
          {newsItem.date && <Text type="secondary">{new Date(newsItem.date).toLocaleDateString()}</Text>}
          {newsItem.source_name && (
            <Text type="secondary">{newsItem.source_name}</Text>
          )}
          {newsItem.url && (
            <Tooltip title="查看原文">
              <a href={newsItem.url} target="_blank" rel="noopener noreferrer" style={{ color: 'inherit', display: 'inline-flex', alignItems: 'center' }}>
           <LinkOutlined />
              </a>
            </Tooltip>
           )}
          {/* Category name display removed */}
        </Space>
        {newsItem.summary && <Paragraph type="secondary" style={{ marginBottom: '12px' }}>{newsItem.summary}</Paragraph>}
        <Divider style={{ marginTop: '0px', marginBottom: '12px' }} />
      </div>

      {/* --- Analysis Section (Flexible Height + Scroll) --- */}
      <div style={{
        flexGrow: 1,        // Takes available vertical space
        overflowY: 'auto',   // Enables vertical scrolling *within this div*
        minHeight: 0,       // Crucial: Prevents flex item overflow issues
        paddingRight: '8px', // Space for scrollbar
      }}>
        {isLoading ? ( // Show loading spinner *inside* the scrollable area
           <div style={{ textAlign: 'center', padding: '20px 0' }}>
              <Spin size="small" /> {isStreaming ? "Streaming analysis..." : "Loading analysis..."}
           </div>
        ) : analysisContent ? (
          <Paragraph style={{ whiteSpace: 'pre-wrap', marginBottom: 0 }}>
            {analysisContent}
          </Paragraph>
        ) : (
          <Empty description="No analysis available or generated." image={Empty.PRESENTED_IMAGE_SIMPLE}/>
        )}
      </div>
    </div>
  );
};

export default AnalysisWindowContent;

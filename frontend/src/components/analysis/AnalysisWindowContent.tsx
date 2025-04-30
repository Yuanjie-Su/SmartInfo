import React, { useState, useEffect } from 'react';
import { Typography, Spin, Alert, Space, Divider, Empty } from 'antd';
import { NewsItem } from '@/utils/types';
import * as newsService from '@/services/newsService';
import { handleApiError } from '@/utils/apiErrorHandler';

const { Title, Text, Paragraph } = Typography;

interface AnalysisWindowContentProps {
  newsItemId: number;
}

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
      setAnalysisContent(''); // Clear previous analysis content

      try {
        // Fetch news item details (without content, which is not needed for display)
        const item = await newsService.getNewsById(newsItemId);
        if (!item) {
          setError('News item not found.');
          setIsLoading(false);
          return;
        }
        setNewsItem(item);

        // If analysis already exists, display it
        if (item.analysis) {
          setAnalysisContent(item.analysis);
          setIsLoading(false);
          setIsStreaming(false);
        } else {
          // If analysis doesn't exist, trigger the streaming analysis
          setIsStreaming(true);
          setIsLoading(true); // Keep loading true while streaming

          try {
            // Use the new streaming endpoint
            const response = await newsService.streamAnalysis(newsItemId);

            if (!response.body) {
              throw new Error("Streaming response body is empty.");
            }

            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let receivedContent = '';

            while (true) {
              const { done, value } = await reader.read();
              if (done) {
                break;
              }
              const decodedChunk = decoder.decode(value, { stream: true });
              receivedContent += decodedChunk;
              setAnalysisContent(receivedContent); // Update state with each chunk
            }

            // Final decode to handle any remaining buffered data
            const finalChunk = decoder.decode();
            if (finalChunk) {
              receivedContent += finalChunk;
              setAnalysisContent(receivedContent);
            }

          } catch (streamError) {
            console.error("Streaming analysis failed:", streamError);
            handleApiError(streamError, 'Failed to stream analysis');
            setError('Failed to stream analysis content.');
          } finally {
            setIsStreaming(false);
            setIsLoading(false); // Set loading to false after streaming finishes
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

  }, [newsItemId]); // Rerun effect if newsItemId changes

  return (
    <div style={{ padding: '20px' }}>
      {isLoading && !newsItem ? (
        <div style={{ textAlign: 'center', padding: '50px 0' }}>
          <Spin size="large" tip="Loading news item..." />
        </div>
      ) : error ? (
        <Alert message="Error" description={error} type="error" showIcon />
      ) : newsItem ? (
        <>
          <Title level={3}>{newsItem.title}</Title>
          <Space size={16} wrap style={{ marginBottom: '16px' }}>
            {newsItem.date && <Text type="secondary">{new Date(newsItem.date).toLocaleDateString()}</Text>}
            <Text type="secondary">{newsItem.source_name}</Text>
            <Text type="secondary">{newsItem.category_name}</Text>
          </Space>
          <Paragraph>{newsItem.summary}</Paragraph>

          <Divider />

          <Title level={4}>Analysis</Title>
          {isStreaming && analysisContent === '' && (
             <div style={{ textAlign: 'center', padding: '20px 0' }}>
                <Spin size="small" /> Streaming analysis...
             </div>
          )}
          {analysisContent ? (
            <Paragraph style={{ whiteSpace: 'pre-wrap' }}>{analysisContent}</Paragraph>
          ) : !isLoading && !isStreaming && (
            <Text type="secondary">No analysis available yet.</Text>
          )}
           {isStreaming && analysisContent !== '' && (
             <Text type="secondary" style={{ display: 'block', marginTop: '8px' }}>Streaming...</Text>
           )}
        </>
      ) : (
        <Empty description="Select a news item to view analysis." />
      )}
    </div>
  );
};

export default AnalysisWindowContent;

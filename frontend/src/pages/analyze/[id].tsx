import React from 'react';
import { useRouter } from 'next/router';
import AnalysisWindowContent from '@/components/analysis/AnalysisWindowContent';
import { Typography, Alert } from 'antd';
import withAuth from '@/components/auth/withAuth'; // Import the HOC

const { Title } = Typography;

const AnalyzePage: React.FC = () => {
  const router = useRouter();
  const { id } = router.query;

  // Ensure id is a number
  const newsItemId = typeof id === 'string' ? parseInt(id, 10) : undefined;

  if (router.isReady && newsItemId === undefined) {
    return (
      <div style={{ padding: '20px' }}>
        <Alert
          message="Error"
          description="Invalid news item ID provided."
          type="error"
          showIcon
        />
      </div>
    );
  }

  // Render the AnalysisWindowContent component, passing the newsItemId
  return (
    <div style={{ padding: '20px' }}>
      {newsItemId !== undefined ? (
        <AnalysisWindowContent newsItemId={newsItemId} />
      ) : (
        <div style={{ textAlign: 'center', padding: '50px 0' }}>
           <Title level={4}>Loading...</Title>
        </div>
      )}
    </div>
  );
};

// Wrap the component with the HOC for authentication
export default withAuth(AnalyzePage);

import React from 'react';
import { Modal } from 'antd';
import AnalysisWindowContent from './AnalysisWindowContent';

interface AnalysisModalProps {
  newsItemId: number;
  isOpen: boolean;
  onClose: () => void;
}

const AnalysisModal: React.FC<AnalysisModalProps> = ({ newsItemId, isOpen, onClose }) => {
  return (
    <Modal
      title="News Analysis"
      open={isOpen}
      onCancel={onClose}
      footer={null}
      width={800}
      bodyStyle={{ padding: '0' }}
      destroyOnClose={true}
      maskClosable={true}
    >
      <AnalysisWindowContent newsItemId={newsItemId} />
    </Modal>
  );
};

export default AnalysisModal; 
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
      open={isOpen}
      onCancel={onClose}
      footer={null}
      width={1000}
      styles={{ body: { padding: '0' } }}
      destroyOnClose={true}
      maskClosable={true}
    >
      <AnalysisWindowContent newsItemId={newsItemId} />
    </Modal>
  );
};

export default AnalysisModal; 
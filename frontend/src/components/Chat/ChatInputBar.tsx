import React from 'react';
import { Input, Button } from 'antd';
import { SendOutlined } from '@ant-design/icons';
import styles from '../../styles/ChatInputBar.module.css';

interface ChatInputBarProps {
  inputValue: string;
  onInputChange: (value: string) => void;
  onSendMessage: (message: string) => void;
  loading?: boolean;
}

const ChatInputBar: React.FC<ChatInputBarProps> = ({
  inputValue,
  onInputChange,
  onSendMessage,
  loading,
}) => {
  const handleSendClick = () => {
    if (inputValue.trim()) {
      onSendMessage(inputValue.trim());
    }
  };

  const handleKeyPress = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSendClick();
    }
  };

  return (
    <div className={styles.chatInputContainer}>
      <Input.TextArea
        value={inputValue}
        onChange={(e) => onInputChange(e.target.value)}
        onKeyPress={handleKeyPress}
        placeholder="Type your message..."
        autoSize={{ minRows: 1, maxRows: 5 }}
        className={styles.chatInputTextArea}
        disabled={loading}
      />
      <Button
        type="primary"
        shape="circle"
        icon={<SendOutlined />}
        onClick={handleSendClick}
        disabled={!inputValue.trim() || loading}
        className={styles.sendButton}
      />
    </div>
  );
};

export default ChatInputBar;

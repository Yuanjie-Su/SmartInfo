import React from 'react';
import { Typography, Button, Space, Row, Col } from 'antd';
import ChatInputBar from './ChatInputBar';
import styles from '../../styles/DefaultChatView.module.css';

const { Title, Text } = Typography;

interface DefaultChatViewProps {
  username: string;
  onSuggestionClick: (suggestion: string) => void;
  inputValue: string;
  onInputChange: (value: string) => void;
  onSendMessage: (message: string) => void;
  loading?: boolean;
}

const DefaultChatView: React.FC<DefaultChatViewProps> = ({
  username,
  onSuggestionClick,
  inputValue,
  onInputChange,
  onSendMessage,
  loading,
}) => {
  const suggestions = [
    "Summarize today's top news.",
    "Analyze an article...",
    "What are the latest updates on AI?",
  ];

  return (
    <div className={styles.defaultChatViewContainer}>
      <div className={styles.greetingArea}>
        <Title level={2} className={styles.greetingTitle}>
          Hello, {username}.
        </Title>
        <Text type="secondary" className={styles.subGreeting}>
          What can SmartInfo help you with today?
        </Text>
      </div>

      <div className={styles.suggestionsArea}>
        <Row gutter={[16, 16]} justify="center">
          {suggestions.map((suggestion, index) => (
            <Col key={index}>
              <Button
                className={styles.suggestionCard}
                onClick={() => onSuggestionClick(suggestion)}
              >
                {suggestion}
              </Button>
            </Col>
          ))}
        </Row>
      </div>

      <div className={styles.chatInputArea}>
        <ChatInputBar
          inputValue={inputValue}
          onInputChange={onInputChange}
          onSendMessage={onSendMessage}
          loading={loading}
        />
      </div>
    </div>
  );
};

export default DefaultChatView;

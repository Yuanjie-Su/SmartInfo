import React, { useState } from 'react';
import { Form, Input, Button, Card, Typography, Alert, Spin } from 'antd';
import { UserOutlined, LockOutlined } from '@ant-design/icons';
import { useAuth } from '../context/AuthContext'; // Import the useAuth hook
import styles from '../styles/LoginPage.module.css'; // Create this CSS module for styling

const { Title } = Typography;

const LoginPage: React.FC = () => {
    const { login, loading } = useAuth(); // Get login function and loading state from context
    const [error, setError] = useState<string | null>(null); // Local state for login errors
    const [form] = Form.useForm(); // Ant Design form instance

    const onFinish = async (values: any) => {
        setError(null); // Clear previous errors
        try {
            await login(values.username, values.password);
            // Redirect is handled within the login function in AuthContext
            console.log('Login attempt finished.');
        } catch (err: any) {
            console.error('Login page caught error:', err);
            // Display error message from API or a generic one
            setError(err.message || 'Login failed. Please check your credentials.');
            form.resetFields(['password']); // Clear password field on error
        }
    };

    const onFinishFailed = (errorInfo: any) => {
        console.log('Failed:', errorInfo);
        setError('Please fill in all required fields.');
    };

    return (
        <div className={styles.loginContainer}>
            <Spin spinning={loading} tip="Logging in...">
                <Card className={styles.loginCard}>
                    <Title level={2} style={{ textAlign: 'center', marginBottom: '24px' }}>
                        Login
                    </Title>
                    {error && (
                        <Alert
                            message="Login Error"
                            description={error}
                            type="error"
                            showIcon
                            closable
                            onClose={() => setError(null)} // Allow closing the alert
                            style={{ marginBottom: '24px' }}
                        />
                    )}
                    <Form
                        form={form}
                        name="login_form"
                        initialValues={{ remember: true }}
                        onFinish={onFinish}
                        onFinishFailed={onFinishFailed}
                        autoComplete="off"
                        layout="vertical" // Use vertical layout for labels above inputs
                        disabled={loading} // Disable form while loading
                    >
                        <Form.Item
                            label="Username"
                            name="username"
                            rules={[{ required: true, message: 'Please input your Username!' }]}
                        >
                            <Input prefix={<UserOutlined />} placeholder="Username" />
                        </Form.Item>

                        <Form.Item
                            label="Password"
                            name="password"
                            rules={[{ required: true, message: 'Please input your Password!' }]}
                        >
                            <Input.Password prefix={<LockOutlined />} placeholder="Password" />
                        </Form.Item>

                        {/* Optional: Add Remember me or Forgot password links here if needed */}
                        {/* <Form.Item name="remember" valuePropName="checked" noStyle>
                            <Checkbox>Remember me</Checkbox>
                        </Form.Item>
                        <a className="login-form-forgot" href="">
                            Forgot password
                        </a> */}

                        <Form.Item>
                            <Button type="primary" htmlType="submit" block loading={loading}>
                                Log in
                            </Button>
                        </Form.Item>

                        {/* Optional: Link to Signup page */}
                        {/* Or <a href="/signup">register now!</a> */}
                    </Form>
                </Card>
            </Spin>
        </div>
    );
};

// This page should not require authentication itself
// We'll handle route protection later, ensuring this page is accessible
// export default withAuth(LoginPage); // DO NOT wrap login page with auth HOC

export default LoginPage;

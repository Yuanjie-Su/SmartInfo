import React, { useState } from 'react';
import { Form, Input, Button, Card, Typography, Alert, Spin } from 'antd';
import { UserOutlined, LockOutlined } from '@ant-design/icons';
import { useRouter } from 'next/router';
import { useAuth } from '../context/AuthContext'; // Import the useAuth hook
import styles from '../styles/LoginPage.module.css'; // Reuse the login page styles

const { Title } = Typography;

interface RegisterFormData {
    username: string;
    password: string;
}

const RegisterPage: React.FC = () => {
    const router = useRouter();
    const { signup, loading: authLoading } = useAuth();
    const [error, setError] = useState<string | null>(null);
    const [success, setSuccess] = useState<string | null>(null);
    const [localLoading, setLocalLoading] = useState(false);
    const [form] = Form.useForm();
    
    // Combine local and auth loading states
    const loading = localLoading || authLoading;

    const onFinish = async (values: RegisterFormData) => {
        setError(null);
        setSuccess(null);
        setLocalLoading(true);

        try {
            await signup(values.username, values.password);

            // The signup function in AuthContext now handles auto-login and redirection
            // No need to set success message or redirect here
            form.resetFields();
            
        } catch (err: any) {
            console.error('Registration error:', err);
            setError(err.message || '注册失败，请稍后再试');
            form.resetFields(['password', 'confirmPassword']);
        } finally {
            setLocalLoading(false);
        }
    };

    const onFinishFailed = (errorInfo: any) => {
        console.log('Form validation failed:', errorInfo);
        setError('请填写所有必填字段');
    };

    return (
        <div className={styles.loginContainer}>
            <Spin spinning={loading} tip="处理中...">
                <Card className={styles.loginCard}>
                    <Title level={2} style={{ textAlign: 'center', marginBottom: '24px' }}>
                        注册新账号
                    </Title>
                    
                    {error && (
                        <Alert
                            message="注册错误"
                            description={error}
                            type="error"
                            showIcon
                            closable
                            onClose={() => setError(null)}
                            style={{ marginBottom: '24px' }}
                        />
                    )}
                    
                    {success && (
                        <Alert
                            message="注册成功"
                            description={success}
                            type="success"
                            showIcon
                            style={{ marginBottom: '24px' }}
                        />
                    )}
                    
                    <Form
                        form={form}
                        name="register_form"
                        initialValues={{ remember: true }}
                        onFinish={onFinish}
                        onFinishFailed={onFinishFailed}
                        autoComplete="off"
                        layout="vertical"
                        disabled={loading || !!success}
                    >
                        <Form.Item
                            label="用户名"
                            name="username"
                            rules={[
                                { required: true, message: '请输入用户名' },
                                { min: 3, message: '用户名至少需要3个字符' }
                            ]}
                        >
                            <Input 
                                prefix={<UserOutlined />} 
                                placeholder="请输入用户名" 
                                autoComplete="username"
                            />
                        </Form.Item>

                        <Form.Item
                            label="密码"
                            name="password"
                            rules={[
                                { required: true, message: '请输入密码' },
                                { min: 6, message: '密码至少需要6个字符' }
                            ]}
                            hasFeedback
                        >
                            <Input.Password 
                                prefix={<LockOutlined />} 
                                placeholder="请输入密码"
                                autoComplete="new-password"
                            />
                        </Form.Item>

                        <Form.Item
                            label="确认密码"
                            name="confirmPassword"
                            dependencies={['password']}
                            hasFeedback
                            rules={[
                                { required: true, message: '请确认您的密码' },
                                ({ getFieldValue }) => ({
                                    validator(_, value) {
                                        if (!value || getFieldValue('password') === value) {
                                            return Promise.resolve();
                                        }
                                        return Promise.reject(new Error('两次输入的密码不匹配'));
                                    },
                                }),
                            ]}
                        >
                            <Input.Password 
                                prefix={<LockOutlined />} 
                                placeholder="请再次输入密码"
                                autoComplete="new-password"
                            />
                        </Form.Item>

                        <Form.Item>
                            <Button 
                                type="primary" 
                                htmlType="submit" 
                                block 
                                loading={loading}
                            >
                                注册
                            </Button>
                        </Form.Item>
                        
                        <div style={{ textAlign: 'center', marginTop: '12px' }}>
                            已有账号？ <a href="/login">立即登录</a>
                        </div>
                    </Form>
                </Card>
            </Spin>
        </div>
    );
};

export default RegisterPage;

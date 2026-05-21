import { Component, type ReactNode, type ErrorInfo } from 'react';

interface Props {
    children?: ReactNode;
    fallback?: ReactNode;
}

interface State {
    hasError: boolean;
    error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
    public state: State = {
        hasError: false,
        error: null
    };

    public static getDerivedStateFromError(error: Error): State {
        return { hasError: true, error };
    }

    public componentDidCatch(error: Error, errorInfo: ErrorInfo) {
        console.error('Uncaught error:', error, errorInfo);
    }

    private handleRetry = () => {
        this.setState({ hasError: false, error: null });
    };

    public render() {
        if (this.state.hasError) {
            if (this.props.fallback) return this.props.fallback;
            return (
                <div style={{ padding: '20px', background: 'rgba(239, 68, 68, 0.08)', color: '#ef4444', margin: '8px', borderRadius: '8px', border: '1px solid rgba(239, 68, 68, 0.2)' }}>
                    <h3 style={{ margin: '0 0 8px 0', fontSize: '0.9rem' }}>Component Error</h3>
                    <pre style={{ whiteSpace: 'pre-wrap', fontSize: '0.8em', margin: '0 0 12px 0' }}>{this.state.error?.message}</pre>
                    <button
                        onClick={this.handleRetry}
                        style={{
                            padding: '6px 16px',
                            borderRadius: '6px',
                            border: '1px solid rgba(239, 68, 68, 0.3)',
                            background: 'rgba(239, 68, 68, 0.1)',
                            color: '#ef4444',
                            cursor: 'pointer',
                            fontSize: '0.8rem',
                        }}
                    >
                        Retry
                    </button>
                    <details style={{ marginTop: '10px' }}>
                        <summary style={{ cursor: 'pointer', fontSize: '0.8em' }}>Stack Trace</summary>
                        <pre style={{ whiteSpace: 'pre-wrap', fontSize: '0.75em', marginTop: '4px' }}>{this.state.error?.stack}</pre>
                    </details>
                </div>
            );
        }

        return this.props.children;
    }
}

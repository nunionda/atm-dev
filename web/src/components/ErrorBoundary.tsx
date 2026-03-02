import { Component, type ReactNode, type ErrorInfo } from 'react';

interface Props {
    children?: ReactNode;
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

    public render() {
        if (this.state.hasError) {
            return (
                <div style={{ padding: '20px', background: '#fee', color: '#c00', margin: '20px', borderRadius: '8px' }}>
                    <h2>Something went wrong in the component tree.</h2>
                    <pre style={{ whiteSpace: 'pre-wrap' }}>{this.state.error?.message}</pre>
                    <details style={{ marginTop: '10px' }}>
                        <summary>Stack Trace</summary>
                        <pre style={{ whiteSpace: 'pre-wrap', fontSize: '0.8em' }}>{this.state.error?.stack}</pre>
                    </details>
                </div>
            );
        }

        return this.props.children;
    }
}

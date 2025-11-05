'use client';

import React, { Component, ErrorInfo, ReactNode } from 'react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { AlertCircle } from 'lucide-react';

interface Props {
    children: ReactNode;
    fallback?: ReactNode;
}

interface State {
    hasError: boolean;
    error: Error | null;
    errorInfo: ErrorInfo | null;
}

/**
 * Error Boundary para capturar errores de React
 * Muestra un mensaje amigable en lugar de romper toda la aplicación
 */
export class ErrorBoundary extends Component<Props, State> {
    constructor(props: Props) {
        super(props);
        this.state = {
            hasError: false,
            error: null,
            errorInfo: null,
        };
    }

    static getDerivedStateFromError(error: Error): Partial<State> {
        return {
            hasError: true,
            error,
        };
    }

    componentDidCatch(error: Error, errorInfo: ErrorInfo) {
        // Log error para debugging
        console.error('ErrorBoundary caught an error:', error, errorInfo);
        
        this.setState({
            error,
            errorInfo,
        });

        // Aquí podrías enviar el error a un servicio de logging
        // Por ejemplo: Sentry, LogRocket, etc.
    }

    handleReset = () => {
        this.setState({
            hasError: false,
            error: null,
            errorInfo: null,
        });
    };

    render() {
        if (this.state.hasError) {
            // Si hay un fallback custom, usarlo
            if (this.props.fallback) {
                return this.props.fallback;
            }

            // UI por defecto para errores
            return (
                <div className="flex items-center justify-center min-h-[400px] p-4">
                    <Card className="w-full max-w-md">
                        <CardHeader>
                            <div className="flex items-center gap-2">
                                <AlertCircle className="h-5 w-5 text-destructive" />
                                <CardTitle>Algo salió mal</CardTitle>
                            </div>
                            <CardDescription>
                                Ha ocurrido un error inesperado. Por favor, intenta recargar la página.
                            </CardDescription>
                        </CardHeader>
                        <CardContent className="space-y-4">
                            {process.env.NODE_ENV === 'development' && this.state.error && (
                                <details className="text-sm">
                                    <summary className="cursor-pointer text-muted-foreground mb-2">
                                        Detalles técnicos (solo en desarrollo)
                                    </summary>
                                    <pre className="bg-muted p-2 rounded overflow-auto text-xs">
                                        {this.state.error.toString()}
                                        {this.state.errorInfo?.componentStack}
                                    </pre>
                                </details>
                            )}
                            <div className="flex gap-2">
                                <Button onClick={this.handleReset} variant="outline">
                                    Intentar de nuevo
                                </Button>
                                <Button 
                                    onClick={() => window.location.reload()} 
                                    variant="default"
                                >
                                    Recargar página
                                </Button>
                            </div>
                        </CardContent>
                    </Card>
                </div>
            );
        }

        return this.props.children;
    }
}

/**
 * HOC para envolver componentes con Error Boundary
 */
export function withErrorBoundary<P extends object>(
    Component: React.ComponentType<P>,
    fallback?: ReactNode
) {
    const WrappedComponent = (props: P) => (
        <ErrorBoundary fallback={fallback}>
            <Component {...props} />
        </ErrorBoundary>
    );

    WrappedComponent.displayName = `withErrorBoundary(${Component.displayName || Component.name || 'Component'})`;

    return WrappedComponent;
}


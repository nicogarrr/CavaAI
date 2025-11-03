'use client';

import React, { memo, ReactNode } from 'react';

/**
 * Optimized wrapper for components that don't need frequent re-renders
 * Improves app fluidity by preventing unnecessary re-renders
 */

interface OptimizedWrapperProps {
    children: ReactNode;
    className?: string;
}

const OptimizedWrapper = memo(({ children, className }: OptimizedWrapperProps) => {
    return <div className={className}>{children}</div>;
});

OptimizedWrapper.displayName = 'OptimizedWrapper';

export default OptimizedWrapper;

/**
 * HOC to wrap components with memo for optimization
 */
export function withOptimization<P extends object>(
    Component: React.ComponentType<P>,
    propsAreEqual?: (prevProps: Readonly<P>, nextProps: Readonly<P>) => boolean
) {
    const MemoizedComponent = memo(Component, propsAreEqual);
    MemoizedComponent.displayName = `Optimized(${Component.displayName || Component.name || 'Component'})`;
    return MemoizedComponent;
}

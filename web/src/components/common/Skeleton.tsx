import React from 'react';
import './Skeleton.css';

export const ChartSkeleton: React.FC<{ height?: number }> = ({ height = 400 }) => (
  <div className="skeleton-chart glass-panel" style={{ height }}>
    <div className="skeleton-bar" style={{ width: '60%', height: 12 }} />
    <div className="skeleton-chart-area">
      <div className="skeleton-wave" />
    </div>
    <div className="skeleton-bar" style={{ width: '80%', height: 8 }} />
  </div>
);

export const TableSkeleton: React.FC<{ rows?: number }> = ({ rows = 5 }) => (
  <div className="skeleton-table">
    <div className="skeleton-row skeleton-header">
      {[1, 2, 3, 4].map(i => (
        <div key={i} className="skeleton-bar" style={{ width: `${60 + i * 8}%`, height: 12 }} />
      ))}
    </div>
    {Array(rows).fill(0).map((_, i) => (
      <div key={i} className="skeleton-row">
        {[1, 2, 3, 4].map(j => (
          <div key={j} className="skeleton-bar" style={{ width: `${50 + j * 10}%`, height: 10 }} />
        ))}
      </div>
    ))}
  </div>
);

export const CardSkeleton: React.FC = () => (
  <div className="skeleton-card glass-panel">
    <div className="skeleton-bar" style={{ width: '40%', height: 10 }} />
    <div className="skeleton-bar" style={{ width: '60%', height: 20, marginTop: 8 }} />
    <div className="skeleton-bar" style={{ width: '30%', height: 10, marginTop: 8 }} />
  </div>
);

export const ScoreCardsSkeleton: React.FC = () => (
  <div className="skeleton-score-cards">
    {[1, 2, 3, 4].map(i => (
      <CardSkeleton key={i} />
    ))}
  </div>
);

import { Link } from 'react-router-dom';
import { LineChart, Activity, Calculator, ArrowRight, TrendingUp } from 'lucide-react';
import './SignalOverview.css';

const ASSET_CARDS = [
  {
    title: 'Stocks',
    icon: <LineChart size={28} />,
    to: '/signals/stocks',
    description: '기술적 분석 & 시그널 스캐너',
    features: ['차트 분석', '진입 시그널', '마켓 레짐'],
    color: 'var(--accent-blue, #3b82f6)',
  },
  {
    title: 'Futures',
    icon: <Activity size={28} />,
    to: '/signals/futures',
    description: 'Z-Score & ATR 기반 선물 분석',
    features: ['스캘핑 분석', 'Fabio 전략', 'MTF 분석'],
    color: 'var(--accent-green, #22c55e)',
  },
  {
    title: 'Options',
    icon: <Calculator size={28} />,
    to: '/signals/options',
    description: 'Black-Scholes 옵션 가격 계산',
    features: ['BS 계산기', '그릭스', '프리셋 자산'],
    color: 'var(--accent-purple, #a855f7)',
  },
];

export function SignalOverview() {
  return (
    <div className="signal-overview">
      <div className="signal-overview-header">
        <div className="signal-overview-title">
          <TrendingUp size={28} />
          <h1>Signal Lab</h1>
        </div>
        <p className="signal-overview-subtitle">
          주식 · 선물 · 옵션 매매 신호 분석 & 진입 전략
        </p>
      </div>

      <div className="signal-overview-grid">
        {ASSET_CARDS.map((card) => (
          <Link key={card.title} to={card.to} className="signal-card glass-panel">
            <div className="signal-card-icon" style={{ color: card.color }}>
              {card.icon}
            </div>
            <h2 className="signal-card-title">{card.title}</h2>
            <p className="signal-card-desc">{card.description}</p>
            <ul className="signal-card-features">
              {card.features.map((f) => (
                <li key={f}>{f}</li>
              ))}
            </ul>
            <div className="signal-card-action" style={{ color: card.color }}>
              <span>상세 보기</span>
              <ArrowRight size={16} />
            </div>
          </Link>
        ))}
      </div>
    </div>
  );
}

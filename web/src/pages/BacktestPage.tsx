import { BacktestSection } from '../components/rebalance/BacktestSection';
import { SubNavigation } from '../components/layout/SubNavigation';
import { useAppState } from '../contexts/AppStateContext';

const REVIEW_TABS = [
  { to: '/review/performance', label: 'Performance' },
  { to: '/review/backtest', label: 'Backtest' },
  { to: '/review/rebalance', label: 'Rebalance' },
];

export function BacktestPage() {
  const { activeMarket } = useAppState();

  return (
    <div style={{ maxWidth: 1200, margin: '2rem auto', padding: '0 2rem' }}>
      <SubNavigation tabs={REVIEW_TABS} />
      <div style={{ marginTop: '1.5rem' }}>
        <BacktestSection activeMarket={activeMarket} />
      </div>
    </div>
  );
}

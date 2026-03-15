import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { Navbar } from './components/layout/Navbar';
import { ErrorBoundary } from './components/ErrorBoundary';
import { AppStateProvider } from './contexts/AppStateContext';
import { Home } from './pages/Home';
import { Theory } from './pages/Theory';
import { Dashboard } from './pages/Dashboard';
import { Operations } from './pages/Operations';
import { Risk } from './pages/Risk';
import { Performance } from './pages/Performance';
import { ScalpAnalyzer } from './pages/ScalpAnalyzer';
import { FabioStrategy } from './pages/FabioStrategy';
import { OptionCalculator } from './pages/OptionCalculator';
import { Rebalance } from './pages/Rebalance';
import { SignalOverview } from './pages/SignalOverview';
import { BacktestPage } from './pages/BacktestPage';

function App() {
  return (
    <Router>
      <AppStateProvider>
      <Navbar />
      <ErrorBoundary>
        <Routes>
          {/* Home */}
          <Route path="/" element={<Home />} />

          {/* Signal Lab */}
          <Route path="/signals" element={<SignalOverview />} />
          <Route path="/signals/stocks" element={<Dashboard />} />
          <Route path="/signals/futures" element={<ScalpAnalyzer />} />
          <Route path="/signals/futures/fabio" element={<FabioStrategy />} />
          <Route path="/signals/options" element={<OptionCalculator />} />

          {/* Trading */}
          <Route path="/trading" element={<Navigate to="/trading/operations" replace />} />
          <Route path="/trading/operations" element={<Operations />} />
          <Route path="/trading/risk" element={<Risk />} />

          {/* Review */}
          <Route path="/review" element={<Navigate to="/review/performance" replace />} />
          <Route path="/review/performance" element={<Performance />} />
          <Route path="/review/backtest" element={<BacktestPage />} />
          <Route path="/review/rebalance" element={<Rebalance />} />

          {/* Theory */}
          <Route path="/theory/*" element={<Theory />} />

          {/* Legacy Redirects */}
          <Route path="/dashboard" element={<Navigate to="/signals/stocks" replace />} />
          <Route path="/scalp-analyzer/fabio" element={<Navigate to="/signals/futures/fabio" replace />} />
          <Route path="/scalp-analyzer" element={<Navigate to="/signals/futures" replace />} />
          <Route path="/option-calculator" element={<Navigate to="/signals/options" replace />} />
          <Route path="/operations" element={<Navigate to="/trading/operations" replace />} />
          <Route path="/risk" element={<Navigate to="/trading/risk" replace />} />
          <Route path="/performance" element={<Navigate to="/review/performance" replace />} />
          <Route path="/rebalance" element={<Navigate to="/review/rebalance" replace />} />
        </Routes>
      </ErrorBoundary>
      </AppStateProvider>
    </Router>
  );
}

export default App;

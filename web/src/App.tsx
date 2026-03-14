import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
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
import { FuturesTrading } from './pages/FuturesTrading';

function App() {
  return (
    <Router>
      <AppStateProvider>
      <Navbar />
      <ErrorBoundary>
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/theory/*" element={<Theory />} />
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/operations" element={<Operations />} />
          <Route path="/rebalance" element={<Rebalance />} />
          <Route path="/risk" element={<Risk />} />
          <Route path="/performance" element={<Performance />} />
          <Route path="/futures-trading" element={<FuturesTrading />} />
          <Route path="/scalp-analyzer" element={<ScalpAnalyzer />} />
          <Route path="/scalp-analyzer/fabio" element={<FabioStrategy />} />
          <Route path="/option-calculator" element={<OptionCalculator />} />
        </Routes>
      </ErrorBoundary>
      </AppStateProvider>
    </Router>
  );
}

export default App;

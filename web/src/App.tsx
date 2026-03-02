import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import { Navbar } from './components/layout/Navbar';
import { Home } from './pages/Home';
import { Theory } from './pages/Theory';
import { Dashboard } from './pages/Dashboard';
import { Operations } from './pages/Operations';
import { Risk } from './pages/Risk';
import { Performance } from './pages/Performance';

function App() {
  return (
    <Router>
      <Navbar />
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/theory/*" element={<Theory />} />
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/operations" element={<Operations />} />
        <Route path="/risk" element={<Risk />} />
        <Route path="/performance" element={<Performance />} />
      </Routes>
    </Router>
  );
}

export default App;

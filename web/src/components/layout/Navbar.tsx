import { Link, useLocation } from 'react-router-dom';
import { LineChart, BookOpen, Radio, Shield, BarChart3, ChevronRight, Activity, Calculator, Zap, RefreshCw } from 'lucide-react';
import './Navbar.css';

export function Navbar() {
    const location = useLocation();

    const isActive = (path: string) => location.pathname.startsWith(path);

    return (
        <nav className="navbar glass-panel">
            <div className="nav-container container">
                <Link to="/" className="nav-logo">
                    <div className="logo-icon">
                        <LineChart className="text-gradient" size={24} />
                    </div>
                    <span className="logo-text">ATS <span className="text-secondary">Theory</span></span>
                </Link>

                <div className="nav-links">
                    <Link
                        to="/dashboard"
                        className={`nav-link ${isActive('/dashboard') ? 'active' : ''}`}
                    >
                        <LineChart size={18} />
                        <span>Dashboard</span>
                    </Link>
                    <Link
                        to="/operations"
                        className={`nav-link ${isActive('/operations') ? 'active' : ''}`}
                    >
                        <Radio size={18} />
                        <span>Operations</span>
                    </Link>
                    <Link
                        to="/performance"
                        className={`nav-link ${isActive('/performance') ? 'active' : ''}`}
                    >
                        <BarChart3 size={18} />
                        <span>Performance</span>
                    </Link>
                    <Link
                        to="/risk"
                        className={`nav-link ${isActive('/risk') ? 'active' : ''}`}
                    >
                        <Shield size={18} />
                        <span>Risk</span>
                    </Link>
                    <Link
                        to="/rebalance"
                        className={`nav-link ${isActive('/rebalance') ? 'active' : ''}`}
                    >
                        <RefreshCw size={18} />
                        <span>Rebalance</span>
                    </Link>
                    <Link
                        to="/futures"
                        className={`nav-link ${isActive('/futures') || isActive('/es-futures') || isActive('/futures-trading') || isActive('/esf-scalping') || isActive('/scalp-analyzer') ? 'active' : ''}`}
                    >
                        <Zap size={18} />
                        <span>Futures</span>
                    </Link>
                    <Link
                        to="/option-calculator"
                        className={`nav-link ${isActive('/option-calculator') ? 'active' : ''}`}
                    >
                        <Calculator size={18} />
                        <span>Options</span>
                    </Link>
                    <Link
                        to="/theory"
                        className={`nav-link ${isActive('/theory') ? 'active' : ''}`}
                    >
                        <BookOpen size={18} />
                        <span>Docs</span>
                    </Link>
                </div>

                <div className="nav-actions">
                    <button className="btn-secondary nav-btn">Log In</button>
                    <button className="btn-primary nav-btn">
                        Get Started
                        <ChevronRight size={16} />
                    </button>
                </div>
            </div>
        </nav>
    );
}

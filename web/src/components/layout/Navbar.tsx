import { useState, useRef, useEffect } from 'react';
import { Link, useLocation } from 'react-router-dom';
import {
  LineChart, Crosshair, Radio, Shield, BarChart3,
  Activity, Calculator, BookOpen, ChevronDown,
  LayoutDashboard, RefreshCw, FlaskConical, Menu, X
} from 'lucide-react';
import './Navbar.css';

interface NavGroup {
  label: string;
  prefix: string;
  items: { to: string; icon: React.ReactNode; label: string }[];
}

const NAV_GROUPS: NavGroup[] = [
  {
    label: 'Signal Lab',
    prefix: '/signals',
    items: [
      { to: '/signals', icon: <LayoutDashboard size={16} />, label: 'Overview' },
      { to: '/signals/stocks', icon: <LineChart size={16} />, label: 'Stocks' },
      { to: '/signals/futures', icon: <Activity size={16} />, label: 'Futures' },
      { to: '/signals/options', icon: <Calculator size={16} />, label: 'Options' },
    ],
  },
  {
    label: 'Trading',
    prefix: '/trading',
    items: [
      { to: '/trading/operations', icon: <Radio size={16} />, label: 'Operations' },
      { to: '/trading/risk', icon: <Shield size={16} />, label: 'Risk' },
    ],
  },
  {
    label: 'Review',
    prefix: '/review',
    items: [
      { to: '/review/performance', icon: <BarChart3 size={16} />, label: 'Performance' },
      { to: '/review/backtest', icon: <FlaskConical size={16} />, label: 'Backtest' },
      { to: '/review/rebalance', icon: <RefreshCw size={16} />, label: 'Rebalance' },
    ],
  },
];

export function Navbar() {
  const location = useLocation();
  const [openGroup, setOpenGroup] = useState<string | null>(null);
  const [mobileOpen, setMobileOpen] = useState(false);
  const navRef = useRef<HTMLElement>(null);

  const isGroupActive = (prefix: string) => location.pathname.startsWith(prefix);
  const isItemActive = (to: string) => location.pathname === to;

  const toggleGroup = (label: string) => {
    setOpenGroup(openGroup === label ? null : label);
  };

  // Close dropdown when clicking outside
  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (navRef.current && !navRef.current.contains(e.target as Node)) {
        setOpenGroup(null);
        setMobileOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  // Close dropdown on route change
  useEffect(() => {
    setOpenGroup(null);
    setMobileOpen(false);
  }, [location.pathname]);

  return (
    <nav className="navbar glass-panel" ref={navRef}>
      <div className="nav-container container">
        <Link to="/" className="nav-logo">
          <div className="logo-icon">
            <Crosshair className="text-gradient" size={24} />
          </div>
          <span className="logo-text">ATS</span>
        </Link>

        {/* Mobile hamburger */}
        <button
          className="nav-mobile-toggle"
          onClick={() => setMobileOpen(!mobileOpen)}
          aria-label="Toggle menu"
        >
          {mobileOpen ? <X size={24} /> : <Menu size={24} />}
        </button>

        <div className={`nav-links ${mobileOpen ? 'nav-links--open' : ''}`}>
          <Link
            to="/"
            className={`nav-link ${location.pathname === '/' ? 'active' : ''}`}
          >
            Home
          </Link>

          {NAV_GROUPS.map((group) => (
            <div
              key={group.label}
              className={`nav-group ${isGroupActive(group.prefix) ? 'active' : ''}`}
            >
              <button
                className={`nav-link nav-group-trigger ${isGroupActive(group.prefix) ? 'active' : ''}`}
                onClick={() => toggleGroup(group.label)}
              >
                <span>{group.label}</span>
                <ChevronDown
                  size={14}
                  className={`nav-chevron ${openGroup === group.label ? 'nav-chevron--open' : ''}`}
                />
              </button>

              {openGroup === group.label && (
                <div className="nav-dropdown glass-panel">
                  {group.items.map((item) => (
                    <Link
                      key={item.to}
                      to={item.to}
                      className={`nav-dropdown-item ${isItemActive(item.to) ? 'active' : ''}`}
                    >
                      {item.icon}
                      <span>{item.label}</span>
                    </Link>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>

        {/* Theory icon (right side) */}
        <div className="nav-actions">
          <Link
            to="/theory"
            className={`nav-link nav-theory ${isGroupActive('/theory') ? 'active' : ''}`}
            title="Documentation"
          >
            <BookOpen size={20} />
          </Link>
        </div>
      </div>
    </nav>
  );
}

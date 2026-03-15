import { Link, useLocation } from 'react-router-dom';
import './Navbar.css';

export interface SubNavTab {
  to: string;
  label: string;
}

interface SubNavigationProps {
  tabs: SubNavTab[];
  className?: string;
}

export function SubNavigation({ tabs, className = '' }: SubNavigationProps) {
  const location = useLocation();

  return (
    <div className={`sub-nav ${className}`}>
      {tabs.map((tab) => (
        <Link
          key={tab.to}
          to={tab.to}
          className={`sub-nav-tab ${location.pathname === tab.to ? 'sub-nav-tab--active' : ''}`}
        >
          {tab.label}
        </Link>
      ))}
    </div>
  );
}

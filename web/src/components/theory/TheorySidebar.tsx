import { useState, useMemo } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { Search, ChevronDown, ChevronRight, Menu, X } from 'lucide-react';
import { categories } from '../../lib/theoryDocs';
import './TheorySidebar.css';

export function TheorySidebar() {
  const location = useLocation();
  const [search, setSearch] = useState('');
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({});
  const [mobileOpen, setMobileOpen] = useState(false);

  const filtered = useMemo(() => {
    if (!search.trim()) return categories;
    const q = search.toLowerCase();
    return categories
      .map((cat) => ({
        ...cat,
        docs: cat.docs.filter(
          (d) =>
            d.title.toLowerCase().includes(q) ||
            d.description.toLowerCase().includes(q)
        ),
      }))
      .filter((cat) => cat.docs.length > 0);
  }, [search]);

  const toggleCategory = (key: string) => {
    setCollapsed((prev) => ({ ...prev, [key]: !prev[key] }));
  };

  const isActive = (category: string, slug: string) =>
    location.pathname === `/theory/${category}/${slug}`;

  const sidebar = (
    <>
      <div className="sidebar-search">
        <Search size={16} className="search-icon" />
        <input
          type="text"
          placeholder="Search docs..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
      </div>
      {filtered.map((cat) => (
        <div key={cat.key} className="sidebar-group">
          <button
            className="group-title"
            onClick={() => toggleCategory(cat.key)}
          >
            <span>{cat.label}</span>
            {collapsed[cat.key] ? (
              <ChevronRight size={14} />
            ) : (
              <ChevronDown size={14} />
            )}
          </button>
          {!collapsed[cat.key] && (
            <ul className="group-list">
              {cat.docs.map((doc) => (
                <li key={doc.slug}>
                  <Link
                    to={`/theory/${doc.category}/${doc.slug}`}
                    className={isActive(doc.category, doc.slug) ? 'active' : ''}
                    onClick={() => setMobileOpen(false)}
                  >
                    {doc.title}
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </div>
      ))}
    </>
  );

  return (
    <>
      <button
        className="sidebar-mobile-toggle"
        onClick={() => setMobileOpen(!mobileOpen)}
        aria-label="Toggle sidebar"
      >
        {mobileOpen ? <X size={20} /> : <Menu size={20} />}
      </button>
      {mobileOpen && (
        <div className="sidebar-overlay" onClick={() => setMobileOpen(false)} />
      )}
      <aside className={`theory-sidebar glass-panel ${mobileOpen ? 'open' : ''}`}>
        {sidebar}
      </aside>
    </>
  );
}

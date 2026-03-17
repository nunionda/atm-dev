import { useState, useMemo } from 'react';
import { Link } from 'react-router-dom';
import { Search, Crosshair, Shield, Zap, Package, FileText } from 'lucide-react';
import { categories } from '../../lib/theoryDocs';

const categoryIcons: Record<string, React.ReactNode> = {
  strategies: <Crosshair size={28} />,
  'risk-exit': <Shield size={28} />,
  specialized: <Zap size={28} />,
  products: <Package size={28} />,
  reports: <FileText size={28} />,
};

export function TheoryLanding() {
  const [search, setSearch] = useState('');

  const filtered = useMemo(() => {
    if (!search.trim()) return null;
    const q = search.toLowerCase();
    return categories
      .flatMap((cat) => cat.docs)
      .filter(
        (d) =>
          d.title.toLowerCase().includes(q) ||
          d.description.toLowerCase().includes(q)
      );
  }, [search]);

  return (
    <div className="theory-landing">
      <div className="content-header">
        <h1>ATS Theory & Documentation</h1>
        <p className="lead-text">
          자동매매 시스템의 이론적 기반, 전략 설계, 리스크 관리, 파생상품 규격을 다루는 통합 문서입니다.
        </p>
      </div>

      <div className="landing-search">
        <Search size={18} className="search-icon" />
        <input
          type="text"
          placeholder="Search all documents..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
      </div>

      {filtered ? (
        <div className="search-results">
          {filtered.length === 0 ? (
            <p className="no-results">No documents found for "{search}"</p>
          ) : (
            <ul className="result-list">
              {filtered.map((doc) => (
                <li key={doc.slug}>
                  <Link to={`/theory/${doc.category}/${doc.slug}`} className="result-item glass-panel">
                    <strong>{doc.title}</strong>
                    <span>{doc.description}</span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </div>
      ) : (
        <div className="content-cards">
          {categories.map((cat) => (
            <div key={cat.key} className="doc-card glass-panel">
              <div className="doc-icon text-gradient">{categoryIcons[cat.key]}</div>
              <h3>{cat.label}</h3>
              <p className="card-subtitle">{cat.labelKo} &middot; {cat.docs.length} docs</p>
              <ul className="card-doc-list">
                {cat.docs.map((doc) => (
                  <li key={doc.slug}>
                    <Link to={`/theory/${doc.category}/${doc.slug}`}>{doc.title}</Link>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

import { extractToc } from '../../lib/tocUtils';
import type { TocItem } from '../../lib/tocUtils';
import './DocTableOfContents.css';

interface DocTableOfContentsProps {
  markdown: string;
}

export function DocTableOfContents({ markdown }: DocTableOfContentsProps) {
  const toc = extractToc(markdown);
  const filtered = toc.filter((item) => item.level >= 2 && item.level <= 3);

  if (filtered.length < 2) return null;

  const handleClick = (e: React.MouseEvent<HTMLAnchorElement>, item: TocItem) => {
    e.preventDefault();
    const el = document.getElementById(item.id);
    if (el) {
      el.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  };

  return (
    <nav className="doc-toc">
      <h4 className="doc-toc-title">On this page</h4>
      <ul className="doc-toc-list">
        {filtered.map((item, i) => (
          <li key={`${item.id}-${i}`} className={`doc-toc-item level-${item.level}`}>
            <a href={`#${item.id}`} onClick={(e) => handleClick(e, item)}>
              {item.text}
            </a>
          </li>
        ))}
      </ul>
    </nav>
  );
}

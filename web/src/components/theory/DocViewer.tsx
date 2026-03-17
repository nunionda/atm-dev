import { useParams, Link } from 'react-router-dom';
import { findDoc, findCategory } from '../../lib/theoryDocs';
import { MarkdownRenderer } from './MarkdownRenderer';
import { DocTableOfContents } from './DocTableOfContents';

export function DocViewer() {
  const { category, slug } = useParams<{ category: string; slug: string }>();
  const doc = category && slug ? findDoc(category, slug) : undefined;
  const cat = category ? findCategory(category) : undefined;

  if (!doc || !cat) {
    return (
      <div className="doc-not-found">
        <h2>Document not found</h2>
        <p>The requested document does not exist.</p>
        <Link to="/theory" className="back-link">Back to Docs</Link>
      </div>
    );
  }

  return (
    <div className="doc-viewer-layout">
      <article className="doc-viewer">
        <div className="breadcrumb">
          <Link to="/theory">Docs</Link>
          <span> / </span>
          <span>{cat.label}</span>
          <span> / </span>
          <span>{doc.title}</span>
        </div>
        <MarkdownRenderer content={doc.content} />
      </article>
      <aside className="doc-toc-wrapper">
        <DocTableOfContents markdown={doc.content} />
      </aside>
    </div>
  );
}
